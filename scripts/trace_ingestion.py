#!/usr/bin/env python3
"""Trace the end-to-end storage locations for a single PDF ingestion.

Flow:
  1. PDF raw bytes  →  R2 (or local storage)
  2. Metadata       →  PostgreSQL: documents + document_versions rows
  3. Text blocks    →  PostgreSQL: document_chunks rows  (via digitization pipeline)
  4. Embeddings    →  Qdrant collection  (via rag_index_service)

Usage:
  python scripts/trace_ingestion.py --pdf data/raw/HUST/10232.pdf
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.services.embeddings import content_hash_for_text
from src.ingestion.parser import DocumentParser
from src.ingestion.legal_structure import extract_sections
from src.ingestion.chunker import build_chunks
from src.rag.config import RAGSettings
from src.rag.container import RAGContainer
from src.retrieval.vector_store import VectorRecord



def print_header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_row(label: str, value: str | None = None) -> None:
    if value:
        print(f"  {label:<30} {value}")
    else:
        print(f"  {label}")


# ── Step 1: PDF raw bytes ────────────────────────────────────────────────────

def step1_check_pdf(pdf_path: str) -> dict:
    print_header("STEP 1 — PDF raw bytes")
    path = Path(pdf_path)
    raw_bytes = path.read_bytes()
    size = len(raw_bytes)
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    print_row("File path", str(path))
    print_row("File size", f"{size:,} bytes ({size/1024:.1f} KB)")
    print_row("SHA-256 checksum", checksum)
    print_row("Pages", "N/A (parsed later)")
    return {"path": str(path), "size": size, "checksum": checksum, "raw_bytes": raw_bytes}


# ── Step 2: R2 / object storage ──────────────────────────────────────────────

def step2_storage(raw_bytes: bytes, checksum: str) -> dict:
    print_header("STEP 2 — Object Storage (R2 / LocalFileStorage)")
    import os as _os
    from dotenv import load_dotenv
    _os.chdir(Path(__file__).resolve().parent.parent)
    _dotenv = _os.environ.get
    load_dotenv(".env")

    r2_endpoint = _dotenv("R2_ENDPOINT", "")
    r2_key = _dotenv("R2_ACCESS_KEY_ID", "")
    r2_secret = _dotenv("R2_SECRET_ACCESS_KEY", "")
    r2_bucket = _dotenv("R2_BUCKET_NAME", "")
    r2_placeholder = {"placeholder_key_id", "placeholder-bucket"}

    def is_placeholder(val: str) -> bool:
        return val in r2_placeholder or not val

    if r2_endpoint and not is_placeholder(r2_key) and not is_placeholder(r2_bucket):
        print_row("Driver", "R2FileStorage (Cloudflare R2)")
        print_row("Endpoint", r2_endpoint)
        print_row("Bucket", r2_bucket)

        # Upload to R2 to demonstrate — use bare boto3 client (sync)
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
        )
        test_key = f"trace/{checksum[:16]}/test.pdf"
        print_row("Object key (test)", test_key)
        print_row("Object key format (canonical)",
                  "{tenant}/{document_number}/v{version}/{filename}")
        try:
            client.put_object(
                Bucket=r2_bucket,
                Key=test_key,
                Body=raw_bytes,
                ContentType="application/pdf",
            )
            print_row("Upload", "success")
            resp = client.list_objects_v2(Bucket=r2_bucket, Prefix=test_key)
            print_row("List objects", f"found {resp.get('KeyCount', 0)}")
            client.delete_object(Bucket=r2_bucket, Key=test_key)
            print_row("Cleanup", "deleted test object")
        except Exception as e:
            print_row("ERROR", str(e))
        return {"driver": "R2", "endpoint": r2_endpoint, "bucket": r2_bucket, "key": test_key}
    else:
        print_row("Driver", "LocalFileStorage (fallback)")
        from src.infrastructure.storage.local_file_storage import LocalFileStorage
        from pathlib import Path as _P
        local_root = Path(__file__).resolve().parent.parent / "data" / "storage"
        storage = LocalFileStorage(root_dir=local_root)
        print_row("Root directory", str(local_root))
        test_key = f"trace/{checksum[:16]}/test.pdf"
        print_row("Object key (test)", test_key)
        print_row("Resolved path", str(storage._resolve_path(test_key)))
        return {"driver": "LocalFileStorage", "root": str(local_root), "key": test_key}


# ── Step 3: PostgreSQL — documents + versions ──────────────────────────────────

def step3_db_metadata(pdf_path: str) -> dict:
    print_header("STEP 3 — PostgreSQL: documents + document_versions rows")
    import os as _os
    from dotenv import load_dotenv
    _os.chdir(Path(__file__).resolve().parent.parent)
    load_dotenv(".env")

    db_url = _os.environ.get("DATABASE_URL", "")
    if not db_url:
        print_row("ERROR", "DATABASE_URL not set")
        return {}

    engine = create_engine(db_url.replace("postgresql://", "postgresql+psycopg://", 1))

    # Show schema — query public.* only to avoid column duplicates from
    # any legacy schemas (Phase 4.2 cleanup: rag_legacy dropped).
    with engine.connect() as conn:
        docs_cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'documents' "
            "ORDER BY ordinal_position"
        ))]
        vers_cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'document_versions' "
            "ORDER BY ordinal_position"
        ))]
        chunks_cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'document_chunks' "
            "ORDER BY ordinal_position"
        ))]

    print_row("documents columns", str(docs_cols))
    print_row("document_versions columns", str(vers_cols))
    print_row("document_chunks columns", str(chunks_cols))

    # Count rows — explicit schema qualifier
    with engine.connect() as conn:
        doc_count = conn.execute(text("SELECT count(*) FROM public.documents")).scalar()
        vers_count = conn.execute(text("SELECT count(*) FROM public.document_versions")).scalar()
        chunk_count = conn.execute(text("SELECT count(*) FROM public.document_chunks")).scalar()
        print()
        print_row("documents count", str(doc_count))
        print_row("document_versions count", str(vers_count))
        print_row("document_chunks count", str(chunk_count))

    return {"db_url": db_url[:50] + "..."}


# ── Step 4: Parsing (pypdf) ──────────────────────────────────────────────────

async def step4_parse(pdf_path: str) -> dict:
    print_header("STEP 4 — pypdf parsing")
    import os as _os
    from dotenv import load_dotenv
    _os.chdir(Path(__file__).resolve().parent.parent)
    load_dotenv(".env")

    rag_settings = RAGSettings(
        app_env="development",
        qdrant_url=_os.environ.get("QDRANT_URL", ""),
        qdrant_api_key=_os.environ.get("QDRANT_API_KEY", ""),
        qdrant_collection=_os.environ.get("QDRANT_COLLECTION", "p234_qdrant"),
        embedding_provider=_os.environ.get("EMBEDDING_PROVIDER", "openai"),
        embedding_model=_os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_dimensions=int(_os.environ.get("EMBEDDING_DIMENSIONS", "1536")),
        openai_api_key=_os.environ.get("OPENAI_API_KEY", ""),
    )
    container = RAGContainer(rag_settings)
    parser = container.parser

    raw_bytes = Path(pdf_path).read_bytes()
    # parser.parse() is synchronous — no await
    blocks, warnings = parser.parse(Path(pdf_path).name, raw_bytes)

    print_row("Parser type", type(parser).__name__)
    print_row("Blocks parsed", str(len(blocks)))
    print_row("Warnings", str(len(warnings)))
    if warnings:
        for w in warnings[:3]:
            print_row("  warn", w[:120])

    if blocks:
        sample = blocks[0]
        sample_text = getattr(sample, "text", "") or ""
        print_row("Sample block (first 200 chars)", repr(sample_text[:200]))
        print_row("Block type", type(sample).__name__)
        print_row("Block attrs", str([a for a in dir(sample) if not a.startswith("_")])[:200])

    return {"blocks": blocks, "block_count": len(blocks), "warnings": warnings}


# ── Step 5: Section extraction + Chunking ─────────────────────────────────────

def step5_chunking(blocks: list) -> dict:
    print_header("STEP 5 — Legal structure extraction + Chunking")

    sections = extract_sections(blocks)
    print_row("Sections extracted", str(len(sections)))

    # Build ChunkData objects from build_chunks (returns properly-formed ChunkData)
    try:
        from src.ingestion.chunker import build_chunks
        from src.domain.schemas import DocumentMetadata
        metadata = DocumentMetadata(
            title="trace-test",
            document_number="TRACE-001",
            owner_department="HUST",
            access_level="public",
            allowed_departments=["HUST"],
            version_number=1,
        )
        raw_chunks = build_chunks(
            document_id=str(uuid.uuid4()),
            version_id=str(uuid.uuid4()),
            metadata=metadata,
            sections=sections,
            max_chars=800,
            overlap_chars=100,
        )
        print_row("build_chunks() output", str(len(raw_chunks)))
        for i, c in enumerate(raw_chunks[:3]):
            print_row(f"  Chunk[{i}].text", repr(c.text[:80]))
            print_row(f"  Chunk[{i}].metadata keys", str(list(c.metadata.keys())))
            print_row(f"  Chunk[{i}].embedding_text", repr(c.embedding_text[:60]))
    except Exception as e:
        import traceback
        print_row("build_chunks()", f"ERROR: {e}")
        traceback.print_exc()

    return {"sections": sections, "section_count": len(sections)}


# ── Step 6: Qdrant collection structure ──────────────────────────────────────

def step6_qdrant_structure() -> dict:
    print_header("STEP 6 — Qdrant collection structure")
    import os as _os
    from dotenv import load_dotenv
    _os.chdir(Path(__file__).resolve().parent.parent)
    load_dotenv(".env")
    load_dotenv(".env.rag", override=True)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(
        url=_os.environ.get("QDRANT_URL", ""),
        api_key=_os.environ.get("QDRANT_API_KEY", ""),
    )
    coll_name = _os.environ.get("QDRANT_COLLECTION", "p234_qdrant")

    try:
        info = client.get_collection(coll_name)
        print_row("Collection name", coll_name)
        print_row("Status", info.status)
        print_row("Points count", str(info.points_count))
        v = info.config.params.vectors
        if isinstance(v, dict):
            for name, params in v.items():
                print_row(f"  Vector '{name}'", f"size={params.size}, distance={params.distance}")
        else:
            print_row("Vector config", f"size={v.size}, distance={v.distance}")
    except Exception as e:
        print_row("ERROR", str(e))

    # Sample payload from existing points
    try:
        points, _ = client.scroll(coll_name, limit=2, with_payload=True, with_vectors=False)
        if points:
            print_row("Sample payload keys", str(sorted(points[0].payload.keys())))
            for k, v in sorted(points[0].payload.items()):
                print_row(f"  {k}", str(v)[:80])
    except Exception as e:
        print_row("Scroll ERROR", str(e))

    return {"collection": coll_name}


# ── Step 7: Full ingestion trace (upload → DB → Qdrant) ─────────────────────

async def step7_full_trace(pdf_path: str) -> None:
    print_header("STEP 7 — Full ingestion trace (API upload)")
    import os as _os
    from dotenv import load_dotenv
    _os.chdir(Path(__file__).resolve().parent.parent)
    load_dotenv(".env")

    # Login
    base = "http://localhost:8000/api/v1"
    try:
        r = httpx.post(f"{base}/auth/login",
                       json={"email": "admin@p234.demo", "password": "P234@123", "device_id": "trace-test"},
                       timeout=30)
        r.raise_for_status()
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print_row("Auth", "logged in as admin@p234.demo")
    except Exception as e:
        print_row("ERROR", f"Login failed: {e}")
        return

    # Upload
    filename = Path(pdf_path).name
    doc_number = f"TRACE-{uuid.uuid4().hex[:8].upper()}"
    title = f"Trace Test: {filename}"
    raw_bytes = Path(pdf_path).read_bytes()

    print_row("Uploading PDF", filename)
    print_row("Document number", doc_number)
    print_row("Title", title)

    try:
        r = httpx.post(
            f"{base}/regulatory-documents/upload",
            data={
                "document_number": doc_number,
                "title": title,
                "issued_by": "HUST",
                "issued_date": "2025-01-01",
                "effective_date": "2025-01-01",
                "auto_digitize": "false",
            },
            files={"file": (filename, raw_bytes, "application/pdf")},
            headers=headers,
            timeout=120,
        )
        print_row("Upload HTTP status", str(r.status_code))
        if r.status_code == 201:
            result = r.json()
            doc_id = result.get("id", "N/A")
            version_id = result.get("current_version_id", "N/A")
            print_row("Document ID", doc_id)
            print_row("Version ID", version_id)
            print_row("Object key", result.get("current_version_object_key", "N/A"))
        else:
            print_row("Upload ERROR", r.text[:300])
    except Exception as e:
        print_row("ERROR", str(e))

    print()
    print_row("NOTE: auto_digitize=False — chunks/Qdrant indexing NOT triggered")
    print_row("Run with --digitize to trigger full pipeline")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Trace PDF ingestion storage locations")
    parser.add_argument("--pdf", default="data/raw/HUST/10232.pdf",
                        help="Path to PDF file (default: data/raw/HUST/10232.pdf)")
    parser.add_argument("--skip-step1", action="store_true")
    parser.add_argument("--skip-step2", action="store_true")
    parser.add_argument("--skip-step3", action="store_true")
    parser.add_argument("--skip-step4", action="store_true")
    parser.add_argument("--skip-step5", action="store_true")
    parser.add_argument("--skip-step6", action="store_true")
    parser.add_argument("--skip-step7", action="store_true")
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  P-234 PDF INGESTION STORAGE TRACE                                 ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  PDF: {args.pdf}")

    results = {}

    if not args.skip_step1:
        results["step1"] = step1_check_pdf(args.pdf)

    if not args.skip_step2:
        raw = results.get("step1", {}).get("raw_bytes", b"")
        chk = results.get("step1", {}).get("checksum", "unknown")
        results["step2"] = step2_storage(raw, chk)

    if not args.skip_step3:
        results["step3"] = step3_db_metadata(args.pdf)

    if not args.skip_step6:
        results["step6"] = step6_qdrant_structure()

    if not args.skip_step4:
        results["step4"] = await step4_parse(args.pdf)

    if not args.skip_step5 and results.get("step4"):
        results["step5"] = step5_chunking(results["step4"].get("blocks", []))

    if not args.skip_step7:
        await step7_full_trace(args.pdf)

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  SUMMARY                                                           ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print()
    print("  1. PDF raw bytes")
    print("     → R2 (Cloudflare)  OR  data/storage/  (LocalFileStorage fallback)")
    print("     → Key format: {tenant}/{document_number}/v{version}/{filename}")
    print()
    print("  2. Document metadata")
    print("     → PostgreSQL: documents (id, document_number, title, issued_by, ...)")
    print("     → PostgreSQL: document_versions (id, document_id, version_number, ...)")
    print("     → PostgreSQL: document_chunks (id, version_id, text, chunk_index, ...)")
    print()
    print("  3. Parsed text blocks")
    print("     → pypdf or Docling (configurable)")
    print("     → Output: list of TextBlock objects with .text, .page, .bbox")
    print()
    print("  4. Sections + Chunks")
    print("     → extract_sections() groups blocks by heading hierarchy")
    print("     → build_chunks() splits text into max_chars chunks with overlap")
    print()
    print("  5. Embeddings")
    print("     → Dense: OpenAI text-embedding-3-small (1536 dims)")
    print("     → Sparse: hashed-lexical (BM25-style)")
    print("     → Stored in: Qdrant collection 'p234_qdrant'")
    print("     → Payload keys: tenant_id, document_id, version_id, chunk_id,")
    print("                     document_number, title, content_hash, valid_from, ...")
    print()
    print("  6. Retrieval access control (build_access_filter)")
    print("     → Filters by: tenant_id, status=published, classification,")
    print("                   allowed_units, valid_from/to (date range)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
