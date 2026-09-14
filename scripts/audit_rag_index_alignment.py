"""Audit and optionally repair PostgreSQL-to-Qdrant index parity."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qdrant_client.models import PointIdsList
from sqlalchemy import create_engine, text

from src.domain.schemas import QdrantPayload
from src.rag.config import RAGSettings
from src.retrieval.vector_store import VectorRecord, build_vector_store
from src.services.embeddings import (
    build_resilient_embedding_provider,
    content_hash_for_text,
)
from src.services.sparse_embeddings import build_sparse_embedding_provider

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPLOYED_TABLES = ("document_chunks", "document_versions", "documents")


@dataclass(frozen=True)
class AlignmentReport:
    collection: str
    postgres_count: int
    qdrant_count: int
    missing_ids: tuple[str, ...]
    stale_ids: tuple[str, ...]
    invalid_payload_ids: tuple[str, ...]
    content_hash_mismatch_ids: tuple[str, ...]

    @property
    def aligned(self) -> bool:
        return not any(
            (
                self.missing_ids,
                self.stale_ids,
                self.invalid_payload_ids,
                self.content_hash_mismatch_ids,
            )
        )


def compare_index(
    expected_items: list[dict[str, Any]],
    actual_payloads: dict[str, dict[str, Any]],
    collection: str,
) -> AlignmentReport:
    expected = {str(item["id"]): item for item in expected_items}
    expected_ids = set(expected)
    actual_ids = set(actual_payloads)
    invalid: list[str] = []
    mismatched: list[str] = []
    for chunk_id in sorted(expected_ids & actual_ids):
        payload = actual_payloads[chunk_id]
        try:
            QdrantPayload.model_validate(payload)
        except Exception:  # noqa: BLE001 - aggregate IDs without exposing payload data
            invalid.append(chunk_id)
        expected_hash = (
            expected[chunk_id]["payload"].get("content_hash")
            or content_hash_for_text(expected[chunk_id]["embedding_text"])
        )
        if payload.get("content_hash") != expected_hash:
            mismatched.append(chunk_id)
    return AlignmentReport(
        collection=collection,
        postgres_count=len(expected_ids),
        qdrant_count=len(actual_ids),
        missing_ids=tuple(sorted(expected_ids - actual_ids)),
        stale_ids=tuple(sorted(actual_ids - expected_ids)),
        invalid_payload_ids=tuple(invalid),
        content_hash_mismatch_ids=tuple(mismatched),
    )


def _sync_database_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1).replace(
        "postgresql://", "postgresql+psycopg://", 1
    )


def describe_deployed_schema(settings: RAGSettings) -> dict[str, Any]:
    engine = create_engine(_sync_database_url(settings.database_url), future=True)
    statement = text(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(:table_names)
        ORDER BY table_name, ordinal_position
        """
    )
    status_statement = text(
        """
        SELECT 'processing_status' AS kind, processing_status AS value, count(*)
        FROM public.document_versions GROUP BY processing_status
        UNION ALL
        SELECT 'legal_status' AS kind, legal_status AS value, count(*)
        FROM public.documents GROUP BY legal_status
        ORDER BY kind, value
        """
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                statement, {"table_names": list(DEPLOYED_TABLES)}
            ).all()
            statuses = connection.execute(status_statement).all()
    finally:
        engine.dispose()
    result = {table: [] for table in DEPLOYED_TABLES}
    for table, column in rows:
        result[str(table)].append(str(column))
    result["status_counts"] = [
        {"kind": str(kind), "value": str(value), "count": int(count)}
        for kind, value, count in statuses
    ]
    return result


def _load_expected_items(settings: RAGSettings) -> list[dict[str, Any]]:
    """Read the deployed legacy table names without changing source authority."""
    engine = create_engine(
        _sync_database_url(settings.database_url),
        future=True,
        pool_pre_ping=True,
    )
    statement = text(
        """
        SELECT c.id::text AS id, c.embedding_text, c.content_hash,
               c.metadata_json, c.chunk_index,
               v.id::text AS version_id,
               d.effective_date AS effective_from, NULL::date AS effective_to,
               d.legal_status,
               d.id::text AS document_id, d.document_number, d.title,
               NULL::text AS source_url, d.access_scope AS access_level,
               '[]'::json AS allowed_departments,
               d.issued_by AS owner_department
        FROM public.document_chunks AS c
        JOIN public.document_versions AS v ON v.id = c.version_id
        JOIN public.documents AS d ON d.id = v.document_id
        WHERE lower(v.processing_status) IN ('published', 'indexed')
        ORDER BY v.id, c.chunk_index
        """
    )
    try:
        with engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
    finally:
        engine.dispose()

    items: list[dict[str, Any]] = []
    for row in rows:
        metadata = dict(row["metadata_json"] or {})
        allowed_units = [
            str(value).upper() for value in (row["allowed_departments"] or [])
        ] or ["*"]
        access_level = str(row["access_level"] or "internal").casefold()
        payload = {
            **metadata,
            "tenant_id": metadata.get("tenant_id") or "hust",
            "document_id": row["document_id"],
            "version_id": row["version_id"],
            "chunk_id": row["id"],
            "owner_unit": metadata.get("owner_unit") or row["owner_department"],
            "allowed_roles": metadata.get("allowed_roles") or ["*"],
            "allowed_units": metadata.get("allowed_units") or allowed_units,
            "classification": metadata.get("classification")
            or ("restricted" if access_level == "restricted" else "internal"),
            "status": "published",
            "legal_status": (
                str(row["legal_status"]).casefold()
                if str(row["legal_status"]).casefold() != "draft"
                else "effective"
            ),
            "valid_from": row["effective_from"] or "1970-01-01T00:00:00Z",
            "valid_to": row["effective_to"],
            "document_number": row["document_number"],
            "title": row["title"],
            "source_url": row["source_url"],
            "content_hash": row["content_hash"],
            "embedding_model": settings.embedding_model,
            "embedding_version": settings.embedding_version,
            "sparse_model": settings.sparse_embedding_model,
            "sparse_version": settings.sparse_embedding_version,
            "index_version": settings.qdrant_collection,
            "chunk_index": row["chunk_index"],
        }
        items.append(
            {
                "id": row["id"],
                "embedding_text": row["embedding_text"],
                "payload": payload,
            }
        )
    return items


async def _read_qdrant(store) -> dict[str, dict[str, Any]]:
    if not hasattr(store, "client") or not hasattr(store, "collection"):
        raise RuntimeError("Index alignment audit requires the Qdrant backend.")
    if not await store.collection_exists():
        return {}
    payloads: dict[str, dict[str, Any]] = {}
    offset = None
    while True:
        points, offset = await store.client.scroll(
            collection_name=store.collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payloads[str(point.id)] = dict(point.payload or {})
        if offset is None:
            break
    return payloads


async def run(*, repair: bool) -> tuple[AlignmentReport, int | None]:
    settings = RAGSettings(
        _env_file=(PROJECT_ROOT / ".env.rag", PROJECT_ROOT / ".env")
    )
    if settings.vector_backend != "qdrant":
        raise RuntimeError("VECTOR_BACKEND must be qdrant for this audit.")
    embeddings = build_resilient_embedding_provider(settings)
    sparse_provider = build_sparse_embedding_provider(settings)
    store = build_vector_store(settings, embeddings.dimensions)
    expected = _load_expected_items(settings)
    actual = await _read_qdrant(store)
    report = compare_index(expected, actual, settings.qdrant_collection)
    repaired_count: int | None = None
    if repair and not report.aligned:
        repair_ids = set(report.missing_ids) | set(report.invalid_payload_ids) | set(
            report.content_hash_mismatch_ids
        )
        repair_items = [item for item in expected if item["id"] in repair_ids]
        records: list[VectorRecord] = []
        if repair_items:
            content_hashes = [
                item["payload"]["content_hash"] for item in repair_items
            ]
            dense_vectors = await embeddings.embed_documents(
                [item["embedding_text"] for item in repair_items],
                content_hashes=content_hashes,
            )
            sparse_vectors = sparse_provider.sparse_embed_documents(
                [item["embedding_text"] for item in repair_items]
            )
            for item, dense, sparse in zip(
                repair_items, dense_vectors, sparse_vectors, strict=True
            ):
                payload = {
                    **item["payload"],
                    "embedding_model": embeddings.model_name,
                    "embedding_version": embeddings.model_version,
                    "sparse_model": sparse_provider.model_name,
                    "sparse_version": sparse_provider.model_version,
                    "sparse_vector": {
                        "indices": list(sparse.indices),
                        "values": list(sparse.values),
                    },
                }
                records.append(
                    VectorRecord(id=item["id"], vector=dense, payload=payload)
                )
            await store.upsert(records)
        repaired_count = len(records)
        if report.stale_ids:
            await store.client.delete(
                collection_name=settings.qdrant_collection,
                points_selector=PointIdsList(points=list(report.stale_ids)),
                wait=True,
            )
        actual = await _read_qdrant(store)
        report = compare_index(expected, actual, settings.qdrant_collection)
    return report, repaired_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Re-upsert PostgreSQL chunks and delete only explicitly stale point IDs.",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument("--describe-schema", action="store_true")
    args = parser.parse_args()
    if args.describe_schema:
        settings = RAGSettings(
            _env_file=(PROJECT_ROOT / ".env.rag", PROJECT_ROOT / ".env")
        )
        print(json.dumps(describe_deployed_schema(settings), indent=2))
        return 0
    report, repaired_count = asyncio.run(run(repair=args.repair))
    full_report = asdict(report)
    payload = {
        "collection": report.collection,
        "postgres_count": report.postgres_count,
        "qdrant_count": report.qdrant_count,
        "missing_count": len(report.missing_ids),
        "stale_count": len(report.stale_ids),
        "invalid_payload_count": len(report.invalid_payload_ids),
        "content_hash_mismatch_count": len(report.content_hash_mismatch_ids),
        "samples": {
            key: list(full_report[key][:20])
            for key in (
                "missing_ids",
                "stale_ids",
                "invalid_payload_ids",
                "content_hash_mismatch_ids",
            )
        },
        "aligned": report.aligned,
        "repaired_count": repaired_count,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report.aligned else 1


if __name__ == "__main__":
    raise SystemExit(main())
