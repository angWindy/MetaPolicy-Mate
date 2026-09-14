#!/usr/bin/env python3
"""Normalize tenant_id in Qdrant from UPPERCASE to lowercase.

Background:
    rag_index_service.index_chunks used to write tenant_id in
    UPPERCASE for DEPARTMENT-scope documents (e.g. "HUST", "HUCE")
    while update_document_access / reindex_section used lowercase.
    The retrieval-side filter (security/policy.py) reads
    user.tenant_id from actor.department.lower() and only ever
    matched the lowercase form, so existing indexed chunks were
    unreachable by search.

This script rewrites the tenant_id payload field on every chunk
that has an UPPERCASE department code in tenant_id, preserving
all other payload fields. Re-embedding is unnecessary — only
payload metadata is touched.

Idempotent: chunks that already have a lowercase or "public"
tenant_id are left alone.

Usage:
    python scripts/normalize_qdrant_tenant_id.py            # dry-run
    python scripts/normalize_qdrant_tenant_id.py --apply     # commit
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, PayloadSchemaType


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def _load_settings() -> tuple[str, str]:
    url = os.environ.get("QDRANT_URL") or os.environ.get("P234_QDRANT_URL")
    key = os.environ.get("QDRANT_API_KEY") or os.environ.get("P234_QDRANT_API_KEY")
    if not url or not key:
        sys.exit(
            "QDRANT_URL / QDRANT_API_KEY must be set (or P234_*-prefixed equivalents)."
        )
    return url, key


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"hust", "huce", "public"}:
        return lowered
    return value


def _is_dirty(value: str | None) -> bool:
    return value is not None and value != value.lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit payload updates (default: dry-run only)",
    )
    parser.add_argument(
        "--collection",
        default="p234_qdrant",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
    )
    args = parser.parse_args()

    url, key = _load_settings()
    collection = args.collection

    client = QdrantClient(url=url, api_key=key, timeout=60.0)

    if not client.collection_exists(collection_name=collection):
        sys.exit(f"Collection '{collection}' does not exist.")

    # Ensure tenant_id is indexed as keyword so the equality filter
    # below is fast. The schema is shared with QdrantPayload so this
    # is just defensive.
    try:
        client.create_payload_index(
            collection_name=collection,
            field_name="tenant_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception:
        # Already exists — fine.
        pass

    # Iterate all points that have an UPPERCASE-or-mixed tenant_id.
    # MatchAny on the known set of dirty values keeps the scan narrow.
    dirty_values = ["HUST", "HUCE", "Public", "PUBLIC"]
    page_token = None
    inspected = 0
    dirty_points: list[tuple[str, str]] = []  # (point_id, normalized_tenant)

    while True:
        scroll_result = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="tenant_id",
                        match=MatchAny(any=dirty_values),
                    ),
                ],
            ),
            limit=args.batch_size,
            offset=page_token,
            with_payload=["tenant_id", "document_number"],
        )
        points, next_token = scroll_result
        if not points:
            break

        for point in points:
            inspected += 1
            current = (point.payload or {}).get("tenant_id")
            normalized = _normalize(current)
            if normalized is None or normalized == current:
                continue
            if not _is_dirty(current):
                continue
            dirty_points.append((str(point.id), normalized))

        page_token = next_token
        if page_token is None:
            break

    log.info(
        "inspected=%d dirty=%d apply=%s",
        inspected,
        len(dirty_points),
        args.apply,
    )

    if not args.apply:
        log.info("dry-run only; pass --apply to commit")
        return 0

    updated = 0
    started = time.perf_counter()
    for point_id, new_tenant in dirty_points:
        client.set_payload(
            collection_name=collection,
            payload={"tenant_id": new_tenant},
            points=[point_id],
            wait=True,
        )
        updated += 1
    elapsed = (time.perf_counter() - started) * 1000
    log.info(
        "updated=%d in %.1fms (avg %.1fms/point)",
        updated,
        elapsed,
        elapsed / max(updated, 1),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
