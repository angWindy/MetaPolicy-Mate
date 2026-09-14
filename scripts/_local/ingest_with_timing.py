"""Run the RAG ingestion pipeline for every HUST PDF and time each stage.

Workflow:

1. (Optional) Truncate the RAG tables in Postgres and drop the Qdrant
   collection. Pass ``--skip-wipe`` to ingest into an already-warm database.
2. For each PDF in ``data/raw/HUST``:
   * run the production rule extractor to derive ``document_number`` and
     ``title`` from the actual PDF content (filename hint keeps the
     ``<n>/QĐ-ĐHBK`` suffix canonical)
   * persist metadata + sections + chunks into Postgres
   * approve + index chunks into Qdrant
   * publish the version so retrieval picks it up
3. Print per-file timings and aggregate totals.

Optional user overrides live in ``data/raw/HUST/metadata_overrides.json``
with shape ``{"<stem>": {"document_number": "...", "title": "..."}}``.
The override is only used when the rule extractor falls back to a generic
title or returns ``needs_human_review=True`` — otherwise the rule wins so
re-ingestion stays deterministic against the file content.

The script reuses ``RAGContainer`` and the production ingestion service so
the measurement reflects the real pipeline.

Run from the project root with the p234 conda env on PATH:

    PYTHONPATH=. python scripts/ingest_with_timing.py --approve-publish
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.domain.schemas import DocumentMetadata, ProcessingStatus  # noqa: E402
from src.ingestion.metadata_extractor import (  # noqa: E402
    MetadataExtractionResult,
    extract_metadata,
)
from src.rag.config import RAGSettings  # noqa: E402
from src.rag.container import RAGContainer  # noqa: E402


def _load_user_overrides(data_dir: Path) -> dict[str, dict[str, str]]:
    """Read ``metadata_overrides.json`` if present.

    The file is opt-in: if it does not exist the rule extractor is the sole
    source of truth, which is what we want for a fresh data drop.
    """
    path = data_dir / "metadata_overrides.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[overrides] WARNING: {path} is not valid JSON ({exc}); ignoring", flush=True)
        return {}
    if not isinstance(loaded, dict):
        print(f"[overrides] WARNING: {path} root must be an object; ignoring", flush=True)
        return {}
    return {str(k): v for k, v in loaded.items() if isinstance(v, dict)}


_TABLE_STEM_SUFFIXES = ("-table", "_table", "-bang", "_bang")


def _is_table_variant(stem: str) -> bool:
    """Return True for filenames that are table-processing test variants.

    The operator may rename canonical PDFs with a ``-table`` suffix (or the
    Vietnamese ``-bang``) to keep a copy around for table-extraction tests.
    Such variants must NOT share ``document_number`` with the production
    QĐ-ĐHBK corpus, otherwise two different physical files collide on the
    unique key and the second one fails to ingest.
    """
    return any(stem.endswith(suf) for suf in _TABLE_STEM_SUFFIXES)


def _strip_table_suffix(stem: str) -> tuple[str, str]:
    """Split a ``<n>-table`` style stem into ``(<n>, "<suffix>")``.

    Falls back to ``(stem, "")`` when the stem is not a table variant. Used
    so the ingest driver can build a deterministic ``<n>/TABLE-...`` number
    for test variants without conflating them with the production corpus.
    """
    for suf in _TABLE_STEM_SUFFIXES:
        if stem.endswith(suf):
            base = stem[: -len(suf)]
            return base, suf.lstrip("-_").upper()
    return stem, ""


def _build_metadata(
    path: Path,
    rule: MetadataExtractionResult,
    user_overrides: dict[str, dict[str, str]],
) -> DocumentMetadata:
    """Compose DocumentMetadata from rule extractor + optional user override.

    Strategy:

    * Table-variant filenames (``<n>-table`` / ``<n>_table`` / ``<n>-bang``)
      get a dedicated ``TABLE-...`` suffix so they never collide with the
      production QĐ-ĐHBK corpus. The base number still comes from the rule
      extractor, falling back to the filename stem.
    * User override for ``document_number`` / ``title`` is honoured when the
      rule extractor is unsure (``needs_human_review=True``) or returned no
      useful title. This lets the operator patch OCR failures without
      re-deriving everything by hand.
    * Otherwise the rule extractor is the source of truth (deterministic
      re-ingest of the same file).
    * If the rule extractor still returns no document_number, the filename
      stem drives ``<stem>/QĐ-ĐHBK`` so the version still has a unique key.
    """
    stem = path.stem
    override = user_overrides.get(stem, {})
    table_stem, table_suffix = _strip_table_suffix(stem)
    is_table_variant = bool(table_suffix)

    document_number = rule.document_number if rule.document_number else None
    if (
        (not document_number or rule.document_number_confidence < 0.7)
        and "document_number" in override
    ):
        document_number = override["document_number"]
    if not document_number:
        # Last-resort fallback. For table variants prefer the bare stem number
        # (e.g. ``2048``) so the resulting ``<n>/TABLE-...`` stays close to
        # the operator's mental model.
        base = table_stem if is_table_variant else stem
        suffix = f"{table_suffix}-ĐHBK" if is_table_variant else "QĐ-ĐHBK"
        document_number = f"{base}/{suffix}"
    if is_table_variant and document_number:
        # Table-variant filenames must NOT share ``document_number`` with the
        # production QĐ-ĐHBK corpus. The rule extractor (now helped by the
        # filename hint) would happily hand us ``10714/QĐ-ĐHBK``; we always
        # rewrite to a ``TABLE-...`` suffix for these files so two physically
        # distinct documents cannot collide on the unique key.
        if "TABLE" not in document_number:
            document_number = f"{table_stem}/{table_suffix}-ĐHBK"

    title = (
        rule.title.title
        if rule.title and rule.title.title and not rule.title.needs_human_review
        else None
    )
    if title is not None and override.get("title"):
        # Honour the user override even when the rule extractor returned a
        # confident but obviously-wrong title (e.g. it picked a parenthetical
        # fragment as the heading). The override is always authoritative for
        # title because it represents the operator's verified metadata.
        title = None
    if title is None and rule.title and rule.title.title and override.get("title"):
        # Rule got a title but the operator provided one; keep the rule's
        # confidence review flag but use the override title.
        title = None
    if title is None and "title" in override:
        title = override["title"]
    if not title:
        title = f"Văn bản số {stem}"

    # Vietnamese university titles can run to several lines when the
    # parenthetical spans the page. Trim at the first sentence boundary past
    # 180 characters so the persisted title stays readable in the UI even
    # when the rule extractor over-matched a body block.
    title = _trim_title(title)

    return DocumentMetadata(
        title=title,
        document_number=document_number,
        issued_by="Đại học Bách khoa Hà Nội",
        owner_department="ĐT",
        access_level="internal",
        version_number=1,
        source_url=str(path.resolve()),
    )


def _trim_title(title: str, *, max_len: int = 240) -> str:
    """Trim an over-long title at the first sentence/phrase boundary.

    Titles shorter than ``max_len`` are returned unchanged. Beyond that we
    look for the last sentence terminator (``";"``, ``":"``, ``"."``,
    ``"\n"``) inside the first ``max_len`` characters; if found, cut there;
    otherwise hard-truncate and append an ellipsis so the UI does not show a
    500-character block.
    """
    if len(title) <= max_len:
        return title
    head = title[:max_len]
    for sep in (";\n", ":\n", ".\n", ";", ":", ".", "\n"):
        idx = head.rfind(sep)
        if idx >= max_len // 2:
            return head[: idx + 1].rstrip() + ("…" if sep in {".\n", ".\n"} else "")
    return head.rstrip() + "…"


def wipe_database() -> None:
    """Truncate Postgres rag tables; the caller is responsible for Qdrant."""
    import psycopg

    conn = psycopg.connect("postgresql://p234:p234@localhost:5432/p234")
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for table in (
                "audit_logs",
                "approval_records",
                "ingestion_jobs",
                "document_relations",
                "access_policies",
                "user_feedback",
                "chunks",
                "sections",
                "document_versions",
                "documents",
            ):
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
        print("[wipe] Postgres tables truncated", flush=True)
    finally:
        conn.close()


def wipe_qdrant(settings: RAGSettings) -> None:
    """Delete the configured Qdrant collection."""
    import requests

    base = settings.qdrant_url.rstrip("/")
    collection = settings.qdrant_collection
    requests.delete(f"{base}/collections/{collection}", timeout=10)
    print(f"[wipe] Qdrant collection {collection} deleted", flush=True)


async def _process(
    container: RAGContainer,
    path: Path,
    *,
    approve_publish: bool,
    user_overrides: dict[str, dict[str, str]],
) -> dict:
    overall_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()

    result: dict = {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "checksum": checksum,
    }

    existing = container.repository.find_version_by_checksum(checksum)

    if existing is None:
        # Stage 1: parse only — we need the rule extractor before calling ingest
        # because the rule extractor drives the document_number we pass in.
        t0 = time.perf_counter()
        blocks, parser_warnings = container.parser.parse(
            path.name, path.read_bytes()
        )
        rule: MetadataExtractionResult = extract_metadata(
            blocks, filename_hint=path.name
        )
        timings["parse"] = time.perf_counter() - t0
        print(f"    ⏱  parse              {timings['parse']*1000:8.1f} ms", flush=True)

        metadata = _build_metadata(path, rule, user_overrides)
        result["rule_rationale"] = rule.rationale
        result["rule_doc_number"] = rule.document_number
        result["rule_doc_number_confidence"] = rule.document_number_confidence
        result["rule_title"] = rule.title.title if rule.title else None
        result["rule_needs_human_review"] = rule.needs_human_review
        result["final_document_number"] = metadata.document_number
        result["final_title"] = metadata.title

        # Stage 2: full ingest (section + chunk + persist + storage).
        t0 = time.perf_counter()
        ingest_result = await container.ingestion.ingest(
            path.name, path.read_bytes(), metadata
        )
        timings["ingest_full"] = time.perf_counter() - t0
        print(
            f"    ⏱  ingest (parse→DB)  {timings['ingest_full']*1000:8.1f} ms",
            flush=True,
        )
        version_id = ingest_result.version_id
        result.update(
            sections=ingest_result.section_count,
            chunks=ingest_result.chunk_count,
            warnings=ingest_result.warnings,
            version_id=version_id,
        )
    else:
        version_id = existing.id
        timings["ingest_full"] = 0.0
        timings["parse"] = 0.0
        result["status"] = "existing"
        result["version_id"] = version_id
        result["final_document_number"] = existing.document_id and None  # see below
        # Hydrate the document number for the report.
        with container.repository.session_factory() as session:
            from src.db.models import Document
            doc = session.get(Document, existing.document_id)
            if doc is not None:
                result["final_document_number"] = doc.document_number
                result["final_title"] = doc.title
        print("    ⏱  parse + ingest     skipped — already ingested", flush=True)

    version = container.repository.get_version(version_id)
    if not approve_publish or version is None:
        timings["total"] = time.perf_counter() - overall_t0
        result["timings_ms"] = {k: round(v * 1000, 1) for k, v in timings.items()}
        return result

    # Stage 3: approve
    t0 = time.perf_counter()
    if version.processing_status == ProcessingStatus.REVIEW_REQUIRED.value:
        version = container.repository.approve_version(
            version_id, approved_by="timing-runner"
        )
        result["approved"] = True
    timings["approve"] = time.perf_counter() - t0
    print(f"    ⏱  approve            {timings['approve']*1000:8.1f} ms", flush=True)

    # Stage 4: embed + upsert (Qdrant indexing)
    t0 = time.perf_counter()
    if version.processing_status == ProcessingStatus.APPROVED.value:
        indexed = await container.ingestion.index_approved_version(version_id)
        result["indexed_chunks"] = indexed
        version = container.repository.get_version(version_id)
    timings["index"] = time.perf_counter() - t0
    print(f"    ⏱  index (embed+upsert) {timings['index']*1000:8.1f} ms", flush=True)

    # Stage 5: publish
    t0 = time.perf_counter()
    if version and version.processing_status in {
        ProcessingStatus.APPROVED.value,
        ProcessingStatus.INDEXED.value,
    }:
        version = container.repository.publish_version(version_id)
        result["published"] = True
    timings["publish"] = time.perf_counter() - t0
    print(f"    ⏱  publish            {timings['publish']*1000:8.1f} ms", flush=True)

    timings["total"] = time.perf_counter() - overall_t0
    result["timings_ms"] = {k: round(v * 1000, 1) for k, v in timings.items()}
    result["processing_status"] = version.processing_status if version else None
    result["legal_status"] = version.legal_status if version else None
    return result


def _collect_summary(rows: list[dict]) -> dict:
    parse_ms = [r["timings_ms"].get("parse", 0) for r in rows if "timings_ms" in r]
    ingest_ms = [r["timings_ms"].get("ingest_full", 0) for r in rows if "timings_ms" in r]
    index_ms = [r["timings_ms"].get("index", 0) for r in rows if "timings_ms" in r]
    total_ms = [r["timings_ms"].get("total", 0) for r in rows if "timings_ms" in r]

    def stats(values: list[float]) -> dict:
        return {
            "count": len(values),
            "min_ms": round(min(values), 1) if values else 0,
            "max_ms": round(max(values), 1) if values else 0,
            "avg_ms": round(statistics.fmean(values), 1) if values else 0,
            "median_ms": round(statistics.median(values), 1) if values else 0,
            "total_ms": round(sum(values), 1) if values else 0,
        }

    return {
        "parse": stats(parse_ms),
        "ingest_full": stats(ingest_ms),
        "index": stats(index_ms),
        "total": stats(total_ms),
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest HUST PDFs with per-stage timing.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw" / "HUST")
    parser.add_argument(
        "--file", action="append", help="PDF filename; repeat to ingest several."
    )
    parser.add_argument(
        "--approve-publish",
        action="store_true",
        help="Approve, index and publish after parsing.",
    )
    parser.add_argument(
        "--skip-wipe",
        action="store_true",
        help="Skip the Postgres + Qdrant reset before ingestion.",
    )
    parser.add_argument(
        "--parser-backend",
        default="auto",
        choices=["auto", "pypdf", "pypdf_table", "docling"],
    )
    parser.add_argument("--ocr", action="store_true", help="Force OCR pipeline on.")
    parser.add_argument(
        "--no-ocr",
        dest="ocr_enabled",
        action="store_false",
        help="Disable OCR pipeline (digital PDFs only).",
    )
    parser.set_defaults(ocr_enabled=None)
    parser.add_argument("--ocr-gpu", action="store_true", help="Enable EasyOCR GPU.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "architecture" / "ingest_timing.json",
        help="Where to write the per-file timings + summary JSON.",
    )
    args = parser.parse_args()

    overrides: dict = {
        "parser_backend": args.parser_backend,
        "ocr_gpu": args.ocr_gpu,
    }
    if args.ocr_enabled is not None:
        overrides["ocr_enabled"] = args.ocr_enabled
    elif args.ocr:
        overrides["ocr_enabled"] = True

    settings = RAGSettings(**overrides)

    if not args.skip_wipe:
        wipe_database()
        wipe_qdrant(settings)

    container = RAGContainer(settings)
    user_overrides = _load_user_overrides(args.data_dir)
    if user_overrides:
        print(f"[overrides] loaded {len(user_overrides)} user override(s)", flush=True)

    if args.file:
        paths = [args.data_dir / name for name in args.file]
    else:
        paths = sorted(args.data_dir.glob("*.pdf"))
    if not paths or any(not p.is_file() for p in paths):
        print("No valid PDF input found.", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for path in paths:
        print(f"\n=== {path.name} ({path.stat().st_size/1024:.1f} KiB) ===", flush=True)
        try:
            rows.append(
                await _process(
                    container,
                    path,
                    approve_publish=args.approve_publish,
                    user_overrides=user_overrides,
                )
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {"file": path.name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            )
            import traceback
            traceback.print_exc()

    summary = _collect_summary([r for r in rows if "timings_ms" in r])
    output = {
        "settings": {
            "generator_provider": settings.generator_provider,
            "model_name": settings.model_name,
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
            "parser_backend": settings.parser_backend,
            "ocr_enabled": settings.ocr_enabled,
        },
        "user_overrides": user_overrides,
        "files": rows,
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))

    print("\n=== Summary ===", flush=True)
    print(json.dumps(summary, indent=2))

    return 0 if not any(r.get("status") == "failed" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))