#!/usr/bin/env python3
"""Verify document state across Neon (Postgres), R2 (object storage), and Qdrant.

Run with the document id (UUID) to inspect. Prints a structured snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import boto3
import requests
from botocore.exceptions import ClientError

from src.config import get_settings
from scripts._r2_maintenance import R2Maintenance


def inspect_neon(document_id: str) -> dict[str, Any]:
    """Hit Postgres directly. We use SQLAlchemy text() via a sync engine."""
    from sqlalchemy import create_engine, text

    settings = get_settings()
    url = settings.database_url
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(url, future=True)

    out: dict[str, Any] = {}

    with engine.connect() as conn:
        # documents table
        row = conn.execute(
            text(
                """
                SELECT id, document_number, access_scope,
                       created_at, updated_at
                FROM documents WHERE id = :id
                """
            ),
            {"id": document_id},
        ).mappings().first()
        out["document"] = dict(row) if row else None

        # document_versions
        rows = conn.execute(
            text(
                """
                SELECT id, version_number, processing_status,
                       object_key, source_filename, size_bytes,
                       created_at
                FROM document_versions
                WHERE document_id = :id
                ORDER BY version_number
                """
            ),
            {"id": document_id},
        ).mappings().all()
        out["versions"] = [dict(r) for r in rows]

        # document_departments
        rows = conn.execute(
            text(
                """
                SELECT dd.department_id, d.code, d.name
                FROM document_departments dd
                JOIN departments d ON d.id = dd.department_id
                WHERE dd.document_id = :id
                ORDER BY d.code
                """
            ),
            {"id": document_id},
        ).mappings().all()
        out["document_departments"] = [dict(r) for r in rows]

        # document_sections (link via version_id, not document_id)
        if out["versions"]:
            version_ids = [
                str(v["id"])
                for v in out["versions"]
            ]
            rows = conn.execute(
                text(
                    """
                    SELECT id, version_id, section_number,
                           heading, section_type, page, sort_order
                    FROM document_sections
                    WHERE version_id = ANY(:vids)
                    ORDER BY version_id, sort_order
                    """
                ),
                {"vids": version_ids},
            ).mappings().all()
            out["sections"] = [dict(r) for r in rows]
        else:
            out["sections"] = []

        # document_chunks via sections
        if out["sections"]:
            section_ids = [
                str(s["id"])
                for s in out["sections"]
            ]
            rows = conn.execute(
                text(
                    """
                    SELECT COUNT(*) AS total
                    FROM document_chunks
                    WHERE section_id = ANY(:sids)
                    """
                ),
                {"sids": section_ids},
            ).mappings().first()
            out["chunks_total"] = dict(rows)
        else:
            out["chunks_total"] = {"total": 0}

    engine.dispose()
    return out


def inspect_r2(object_key: str) -> dict[str, Any]:
    settings = get_settings()
    r2 = R2Maintenance(
        endpoint=settings.r2_endpoint,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=settings.r2_secret_access_key,
        bucket_name=settings.r2_bucket_name,
    )
    head = r2.head_object(object_key)
    out: dict[str, Any] = {
        "object_key": object_key,
        "exists": head is not None,
    }
    if head is not None:
        out["size"] = head.get("ContentLength")
        out["etag"] = head.get("ETag")
        out["last_modified"] = str(head.get("LastModified"))
    return out


def inspect_qdrant(document_id: str) -> dict[str, Any]:
    from qdrant_client import QdrantClient

    settings = get_settings()
    client = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ["QDRANT_API_KEY"],
    )
    coll = os.environ["QDRANT_COLLECTION"]
    out: dict[str, Any] = {"collection": coll}

    try:
        client.get_collection(coll)
        out["collection_exists"] = True
    except Exception as exc:
        out["collection_exists"] = False
        out["error"] = str(exc)
        return out

    # Filter points for this document
    res = client.scroll(
        collection_name=coll,
        scroll_filter={
            "must": [
                {"key": "document_id",
                 "match": {"value": document_id}},
            ]
        },
        limit=50,
        with_payload=True,
        with_vectors=False,
    )
    points = res[0]
    out["point_count"] = len(points)
    out["sample_payload"] = (
        points[0].payload if points else None
    )
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--document-id", required=True)
    p.add_argument("--object-key", required=True)
    args = p.parse_args()

    print("=" * 70)
    print("NEON (Postgres)")
    print("=" * 70)
    neon = inspect_neon(args.document_id)
    print(json.dumps(neon, indent=2, ensure_ascii=False, default=str))

    print("\n" + "=" * 70)
    print("R2 (Cloudflare)")
    print("=" * 70)
    r2 = inspect_r2(args.object_key)
    print(json.dumps(r2, indent=2, ensure_ascii=False))

    print("\n" + "=" * 70)
    print("QDRANT")
    print("=" * 70)
    qd = inspect_qdrant(args.document_id)
    print(json.dumps(qd, indent=2, ensure_ascii=False, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())