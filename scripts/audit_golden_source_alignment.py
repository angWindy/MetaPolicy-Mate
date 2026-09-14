"""Read-only audit of sweep labels against the current PostgreSQL corpus."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GOLDEN = PROJECT_ROOT / "tests" / "sweep" / "golden_v4.jsonl"


def _database_url() -> str:
    rag_values = dotenv_values(PROJECT_ROOT / ".env.rag")
    app_values = dotenv_values(PROJECT_ROOT / ".env")
    value = app_values.get("DATABASE_URL") or rag_values.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured")
    url = str(value)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return url


def _load_cases(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _document_key(value: str) -> str:
    primary = value.split("/", 1)[0]
    return re.sub(r"\W+", "", primary.casefold())


def _excerpt(value: str, needle: str, radius: int = 450) -> str:
    folded = value.casefold()
    position = folded.find(needle.casefold())
    if position < 0:
        return value[: radius * 2]
    start = max(0, position - radius)
    end = min(len(value), position + len(needle) + radius)
    return value[start:end]


def audit(
    path: Path,
    excerpt_ids: set[str] | None = None,
    neighbor_radius: int = 0,
) -> list[dict]:
    engine = create_engine(_database_url(), future=True, pool_pre_ping=True)
    statement = text(
        """
        SELECT c.id::text AS chunk_id, c.version_id::text AS version_id,
               c.chunk_index, d.document_number, d.title, c.text
        FROM public.document_chunks AS c
        JOIN public.document_versions AS v ON v.id = c.version_id
        JOIN public.documents AS d ON d.id = v.document_id
        WHERE c.text ILIKE :needle
        ORDER BY d.document_number, c.chunk_index
        LIMIT 5000
        """
    )
    neighbor_statement = text(
        """
        SELECT c.id::text AS chunk_id, c.chunk_index, d.document_number, c.text
        FROM public.document_chunks AS c
        JOIN public.document_versions AS v ON v.id = c.version_id
        JOIN public.documents AS d ON d.id = v.document_id
        WHERE c.version_id = CAST(:version_id AS uuid)
          AND c.chunk_index BETWEEN :minimum_index AND :maximum_index
        ORDER BY c.chunk_index
        """
    )
    results: list[dict] = []
    try:
        with engine.connect() as connection:
            for case in _load_cases(path):
                expected_key = _document_key(case["expected_doc"])
                groups = case.get("source_locator", {}).get("evidence_groups") or [
                    [case["expected_needle"]]
                ]
                group_results: list[dict] = []
                expected_doc_rows_by_id: dict[str, dict] = {}
                all_rows_by_id: dict[str, dict] = {}
                for alternatives in groups:
                    matched_alternative = None
                    matched_expected_rows: list[dict] = []
                    for alternative in alternatives:
                        rows = connection.execute(
                            statement,
                            {"needle": f"%{alternative}%"},
                        ).mappings().all()
                        for row in rows:
                            all_rows_by_id[str(row["chunk_id"])] = row
                        expected_rows = [
                            row
                            for row in rows
                            if expected_key
                            in _document_key(str(row["document_number"]))
                        ]
                        if expected_rows:
                            matched_alternative = alternative
                            matched_expected_rows = expected_rows
                            break
                    for row in matched_expected_rows:
                        expected_doc_rows_by_id[str(row["chunk_id"])] = row
                    group_results.append(
                        {
                            "alternatives": alternatives,
                            "matched_alternative": matched_alternative,
                            "expected_document_present": bool(
                                matched_expected_rows
                            ),
                        }
                    )
                rows = list(all_rows_by_id.values())
                expected_doc_rows = list(expected_doc_rows_by_id.values())
                current_ids = set(all_rows_by_id)
                labelled_ids = set(case.get("expected_chunk_ids", []))
                result = {
                        "id": case["id"],
                        "evidence_groups": groups,
                        "group_results": group_results,
                        "match_count": len(rows),
                        "matched_documents": sorted(
                            {str(row["document_number"]) for row in rows}
                        ),
                        "expected_document_present": all(
                            item["expected_document_present"]
                            for item in group_results
                        ),
                        "current_expected_document_chunk_ids": sorted(
                            {str(row["chunk_id"]) for row in expected_doc_rows}
                        ),
                        "labelled_chunk_ids_current": bool(
                            labelled_ids.intersection(current_ids)
                        ),
                    }
                if excerpt_ids and case["id"] in excerpt_ids:
                    result["expected_document_excerpts"] = [
                        {
                            "chunk_id": str(row["chunk_id"]),
                            "document_number": str(row["document_number"]),
                            "excerpt": _excerpt(
                                str(row["text"]),
                                next(
                                    (
                                        str(item["matched_alternative"])
                                        for item in group_results
                                        if item["matched_alternative"]
                                        and str(item["matched_alternative"]).casefold()
                                        in str(row["text"]).casefold()
                                    ),
                                    "",
                                ),
                            ),
                        }
                        for row in expected_doc_rows
                    ]
                    if neighbor_radius:
                        neighbors: dict[str, dict] = {}
                        for row in expected_doc_rows:
                            nearby = connection.execute(
                                neighbor_statement,
                                {
                                    "version_id": row["version_id"],
                                    "minimum_index": max(
                                        0, int(row["chunk_index"]) - neighbor_radius
                                    ),
                                    "maximum_index": (
                                        int(row["chunk_index"]) + neighbor_radius
                                    ),
                                },
                            ).mappings()
                            for neighbor in nearby:
                                neighbors[str(neighbor["chunk_id"])] = {
                                    "chunk_id": str(neighbor["chunk_id"]),
                                    "chunk_index": int(neighbor["chunk_index"]),
                                    "document_number": str(
                                        neighbor["document_number"]
                                    ),
                                    "text": str(neighbor["text"]),
                                }
                        result["expected_document_neighbors"] = sorted(
                            neighbors.values(), key=lambda item: item["chunk_index"]
                        )
                results.append(result)
    finally:
        engine.dispose()
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--refresh-out",
        type=Path,
        help="Write a copy with chunk IDs refreshed from the current corpus.",
    )
    parser.add_argument(
        "--excerpt-ids",
        help="Comma-separated case IDs whose expected-source excerpts are included.",
    )
    parser.add_argument(
        "--neighbor-radius",
        type=int,
        default=0,
        help="Include this many neighboring chunks around selected excerpts.",
    )
    args = parser.parse_args()

    excerpt_ids = (
        {item.strip() for item in args.excerpt_ids.split(",") if item.strip()}
        if args.excerpt_ids
        else None
    )
    if args.neighbor_radius < 0:
        parser.error("--neighbor-radius must not be negative")
    results = audit(args.golden, excerpt_ids, args.neighbor_radius)
    summary = {
        "total": len(results),
        "source_groups_aligned": sum(
            item["expected_document_present"] for item in results
        ),
        "expected_document_present": sum(
            item["expected_document_present"] for item in results
        ),
        "labelled_chunk_ids_current": sum(
            item["labelled_chunk_ids_current"] for item in results
        ),
    }
    payload = {"summary": summary, "cases": results}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
    if args.refresh_out:
        refreshed_cases = _load_cases(args.golden)
        for case, result in zip(refreshed_cases, results, strict=True):
            case["expected_chunk_ids"] = result[
                "current_expected_document_chunk_ids"
            ]
        args.refresh_out.write_text(
            "".join(
                json.dumps(case, ensure_ascii=False) + "\n"
                for case in refreshed_cases
            ),
            encoding="utf-8",
        )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["source_groups_aligned"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
