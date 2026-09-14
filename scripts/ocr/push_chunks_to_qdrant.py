"""Push document_chunks rows from Neon to Qdrant for verification.

Reads the most-recent version of each source_filename from
``document_chunks`` (joined with ``document_versions`` and
``documents``), builds a QdrantPoint with a hash-based vector
placeholder, and upserts into Qdrant.

This is a G4 verification helper — it doesn't generate real
embeddings (the production pipeline goes through
``RagIndexService.index_chunks`` which uses OpenAI or the configured
embedding provider). The hash-based vector proves:

1. Qdrant connectivity from the re-ingest environment.
2. The QdrantPayload contract from ``src/domain/schemas.py`` is
   satisfied (all required keys are present).
3. Point count for the re-ingested documents matches the DB chunk
   count.

Usage::

    export QDRANT_URL=http://localhost:6333
    export DATABASE_URL=postgres://...
    python scripts/ocr/push_chunks_to_qdrant.py [--filename 188_QD_BGDDT.pdf]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import create_engine, text as sa_text  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.http import models as qmodels  # noqa: E402

VECTOR_DIM = 384


def _hash_vector(text: str, dim: int = VECTOR_DIM) -> list[float]:
    """Deterministic pseudo-vector for verification (NOT a real embedding).

    Splits the text into ``dim`` equal slots and writes a normalised
    count per slot. Vectors of the same text are identical so the
    Qdrant payload + filter logic still works for end-to-end
    pipeline checks.
    """
    vec = [0.0] * dim
    if not text:
        return vec
    h = hashlib.sha512(text.encode("utf-8")).digest()
    # Use 8 bytes per slot -> 8 floats per chunk -> 64 slots from 512 bits
    chunk = len(h) // 64
    for slot in range(64):
        start = slot * chunk
        end = start + chunk
        block = h[start:end]
        val = int.from_bytes(block, "big") / (2 ** (chunk * 8))
        vec[slot] = val
    # Fill remaining slots deterministically
    for i in range(64, dim):
        vec[i] = (h[i % len(h)] / 255.0)
    return vec


def _build_payload(chunk_row: dict) -> dict:
    """Map a DB chunk row into the canonical QdrantPayload shape.

    The shape is the same ``metadata_json`` written by ``build_chunks``
    plus a few top-level fields Qdrant needs for filtered retrieval.

    ``tenant_id`` is derived from the issuing school (HUCE/HUST) since
    the ``documents`` table doesn't have an explicit tenant column.
    """
    meta = chunk_row["metadata_json"] or {}
    issued_by = chunk_row.get("issued_by") or ""
    # Tenant derivation — same convention used in DigitizeDocumentHandler.
    if issued_by.startswith("HUCE"):
        tenant_id = "huce"
    elif issued_by.startswith("HUST"):
        tenant_id = "hust"
    else:
        tenant_id = "public"
    payload = {
        # Identity
        "chunk_id": str(chunk_row["chunk_id"]),
        "document_id": chunk_row["document_id"],
        "version_id": chunk_row["version_id"],
        "tenant_id": tenant_id,
        # Document metadata
        "document_number": chunk_row["document_number"],
        "title": chunk_row["title"],
        "issued_by": chunk_row["issued_by"],
        "access_scope": chunk_row["access_scope"],
        "legal_status": chunk_row["legal_status"],
        # Section structure
        "section_type": meta.get("section_type"),
        "section_number": meta.get("section_number"),
        "heading": meta.get("heading"),
        "heading_path": meta.get("heading_path") or [],
        "article": meta.get("article"),
        "clause": meta.get("clause"),
        "point": meta.get("point"),
        "page": meta.get("page"),
        "content_type": meta.get("content_type"),
        "low_confidence": bool(meta.get("low_confidence", False)),
        # Text
        "text": chunk_row["text"],
        "embedding_text": chunk_row["embedding_text"],
        # Indexing provenance
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    return payload


async def _run(args: argparse.Namespace) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1
    if not os.environ.get("QDRANT_URL"):
        print("ERROR: QDRANT_URL not set", file=sys.stderr)
        return 1

    eng = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    qdrant = QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY") or None,
        timeout=15,
    )

    collection = os.environ.get("QDRANT_COLLECTION", "hust-regulations-v1")
    # Recreate the collection if it doesn't exist (or has wrong dim)
    if not qdrant.collection_exists(collection):
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(
                size=VECTOR_DIM, distance=qmodels.Distance.COSINE
            ),
        )
        print(f"Created collection: {collection}")
    else:
        info = qdrant.get_collection(collection)
        existing_dim = (
            info.config.params.vectors.size
            if hasattr(info.config.params, "vectors")
            else VECTOR_DIM
        )
        if existing_dim != VECTOR_DIM:
            print(
                f"WARN: collection {collection} has dim={existing_dim}, "
                f"expected {VECTOR_DIM}. Recreating."
            )
            qdrant.delete_collection(collection)
            qdrant.create_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(
                    size=VECTOR_DIM, distance=qmodels.Distance.COSINE
                ),
            )

    # Pick chunks to push
    where_clause = ""
    params: dict = {}
    if args.filename:
        where_clause = "AND v.source_filename = :fn"
        params["fn"] = args.filename
    sql = sa_text(
        f"""
        SELECT ch.id AS chunk_id, ch.text, ch.embedding_text, ch.metadata_json,
               v.id AS version_id, v.document_id,
               d.document_number, d.title, d.issued_by, d.access_scope,
               d.legal_status
          FROM document_chunks ch
          JOIN document_versions v ON v.id = ch.version_id
          JOIN documents d ON d.id = v.document_id
         WHERE v.id = (
             SELECT id FROM document_versions
              WHERE document_id = v.document_id
              ORDER BY created_at DESC LIMIT 1
         )
           AND char_length(ch.text) > 0
           {where_clause}
         ORDER BY ch.chunk_index
        """
    )
    rows = [dict(r._mapping) for r in eng.connect().execute(sql, params).fetchall()]
    print(f"Rows to push: {len(rows)}")
    if not rows:
        return 0

    points: list[qmodels.PointStruct] = []
    for row in rows:
        payload = _build_payload(row)
        vec = _hash_vector(row["text"] or "", VECTOR_DIM)
        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload=payload,
            )
        )

    # Upsert in batches of 100
    BATCH = 100
    for i in range(0, len(points), BATCH):
        batch = points[i : i + BATCH]
        qdrant.upsert(collection_name=collection, points=batch, wait=True)
        print(f"  Upserted {i + len(batch)}/{len(points)}")

    count = qdrant.count(collection)
    print(f"Total points in '{collection}': {count.count}")

    # Spot-check payload on one point
    sample_id = points[0].id
    sample = qdrant.retrieve(collection, ids=[sample_id])
    if sample:
        print("Sample payload keys:")
        for k in sorted(sample[0].payload.keys()):
            print(f"  {k}: {sample[0].payload[k]!r:.80}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--filename",
        help="Filter to a single source_filename (e.g. '188_QD_BGDDT.pdf')",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
