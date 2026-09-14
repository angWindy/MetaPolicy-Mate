"""End-to-end test: parse real PDF → chunk → OpenAI embedding → Qdrant upsert.

Verifies that the standalone RAG container can:
1. Parse a real Vietnamese legal PDF (Docling/pypdf).
2. Build chunks respecting the configured chunk_max_chars / overlap.
3. Embed chunks with the real OpenAI text-embedding-3-small API.
4. Upsert the resulting vectors into a real Qdrant collection.

No mocks, no hardcoded vectors - everything is computed from the input PDF.
"""
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.repository import Repository
from src.db.models import Document, DocumentVersion
from src.domain.schemas import (
    AccessScope,
    ChunkData,
    DocumentMetadata,
)
from src.ingestion.chunker import build_chunks
from src.ingestion.legal_structure import extract_sections
from src.ingestion.parser import DocumentParser
from src.rag.config import RAGSettings, get_rag_settings
from src.rag.container import RAGContainer
from src.retrieval.vector_store import VectorRecord
from src.services.embeddings import content_hash_for_text
from src.services.storage import LocalDocumentStorage


async def main(pdf_path: str) -> None:
    print("=== E2E ingestion test ===")
    print(f"PDF: {pdf_path}")
    print(f"Size: {os.path.getsize(pdf_path)} bytes")
    print()

    settings = get_rag_settings()
    print("Settings:")
    print(f"  embedding_provider = {settings.embedding_provider}")
    print(f"  embedding_model    = {settings.embedding_model}")
    print(f"  embedding_dim      = {settings.embedding_dimensions}")
    print(f"  vector_backend     = {settings.vector_backend}")
    print(f"  qdrant_url         = {settings.qdrant_url}")
    print(f"  qdrant_collection  = {settings.qdrant_collection}")
    print(f"  chunk_max_chars    = {settings.chunk_max_chars}")
    print()

    container = RAGContainer(settings)
    # Skip create_all - tables already exist with the tenant DB schema; the
    # RAG module's local SQLite-style tables would conflict with type info.
    # We only need embeddings + Qdrant upsert which don't touch the DB schema.

    # 1) Parse the PDF
    print("--- Step 1: parse PDF ---")
    raw_bytes = Path(pdf_path).read_bytes()
    blocks, parser_warnings = container.parser.parse(Path(pdf_path).name, raw_bytes)
    print(f"  parsed_blocks   = {len(blocks)}")
    print(f"  parser_warnings = {len(parser_warnings)}")
    if parser_warnings:
        for w in parser_warnings[:3]:
            print(f"    warn: {w[:120]}")
    if not blocks:
        print("  ERROR: parser returned 0 blocks")
        return
    sample = blocks[0]
    sample_text = getattr(sample, "text", "") or ""
    print(f"  first_block_text (head) = {sample_text[:200]!r}")
    print()

    # 2) Extract sections
    print("--- Step 2: extract sections ---")
    sections = extract_sections(blocks)
    print(f"  sections = {len(sections)}")
    if sections:
        s0 = sections[0]
        print(f"  first_section: type={s0.section_type}, num={s0.section_number}")
        print(f"    heading = {s0.heading!r}")
        print(f"    text (head) = {s0.text[:200]!r}")
    print()

    # 3) Build chunks
    print("--- Step 3: build chunks ---")
    doc_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    metadata = DocumentMetadata(
        document_number=f"E2E-TEST-{date.today().isoformat()}",
        title=Path(pdf_path).stem,
        version_number=1,
        effective_from=date.today(),
        effective_to=None,
        owner_department="HUST",
        access_level=AccessScope.DEPARTMENT,
        allowed_departments=["HUST", "HUCE"],
        source_url=None,
    )
    chunks = build_chunks(
        document_id=doc_id,
        version_id=version_id,
        metadata=metadata,
        sections=sections,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    print(f"  chunks = {len(chunks)}")
    for i, chunk in enumerate(chunks[:5]):
        print(
            f"    [{i}] id={chunk.id[:8]}.. "
            f"len={len(chunk.text)} "
            f"type={chunk.metadata.get('section_type', '?')} "
            f"num={chunk.metadata.get('section_number', '?')}"
        )
        print(f"        text(head) = {chunk.text[:120]!r}")
    if len(chunks) > 5:
        print(f"    ... and {len(chunks)-5} more chunks")
    print()

    # 4) Embed with OpenAI (real API)
    print("--- Step 4: embed chunks (real OpenAI API) ---")
    content_hashes = [
        content_hash_for_text(chunk.embedding_text) for chunk in chunks
    ]
    vectors = await container.embeddings.embed_documents(
        [chunk.embedding_text for chunk in chunks],
        content_hashes=content_hashes,
    )
    print(f"  vectors = {len(vectors)}")
    print(f"  dim     = {len(vectors[0]) if vectors else 0}")
    # Sanity check: vector is not all-zero / hardcoded
    sample_vec = vectors[0]
    print(f"  v[0][:5] = {sample_vec[:5]}")
    print(f"  v[0] L2 norm = {(sum(x*x for x in sample_vec))**0.5:.4f}")
    print()

    # 5) Upsert into Qdrant (real)
    print("--- Step 5: upsert into Qdrant ---")
    records = []
    for chunk, vector, content_hash in zip(chunks, vectors, content_hashes):
        payload = {
            "document_id": doc_id,
            "version_id": version_id,
            "document_number": metadata.document_number,
            "title": metadata.title,
            "section_type": chunk.metadata.get("section_type"),
            "section_number": chunk.metadata.get("section_number"),
            "heading": chunk.metadata.get("heading"),
            "text": chunk.text,
            "source_pdf": Path(pdf_path).name,
        }
        records.append(VectorRecord(
            id=chunk.id,
            vector=vector,
            payload=payload,
        ))
    await container.vector_store.create_payload_indexes()
    await container.vector_store.upsert(records)
    print(f"  upserted {len(records)} records into collection '{settings.qdrant_collection}'")
    print()

    # 6) Verify collection stats
    print("--- Step 6: verify Qdrant collection ---")
    try:
        info = await container.vector_store.client.get_collection(settings.qdrant_collection)
        print(f"  collection points_count = {info.points_count}")
        print(f"  collection status        = {info.status}")
    except Exception as e:
        print(f"  collection_info error: {e}")

    # 7) Search test (semantic)
    print()
    print("--- Step 7: semantic search test ---")
    query = "Quy định về chấm công"
    qvec = await container.embeddings.embed_query(query)
    print(f"  query = {query!r}")
    print(f"  query_vec dim = {len(qvec)}")
    hits = await container.vector_store.search(
        query_vector=qvec, limit=3,
    )
    print(f"  hits = {len(hits)}")
    for hit in hits:
        chunk_id, score, payload = hit
        print(f"    score={score:.4f}  id={chunk_id[:8]}..")
        print(f"        text(head) = {payload.get('text', '')[:100]!r}")
        print(f"        section = {payload.get('section_type', '?')} {payload.get('section_number', '')}")


if __name__ == "__main__":
    pdf_arg = sys.argv[1] if len(sys.argv) > 1 else "data/raw/HUCE/1145 - Quy định chấm công.pdf"
    asyncio.run(main(pdf_arg))
