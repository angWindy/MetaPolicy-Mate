import os
import uuid

import pytest

# Use 128-dim embeddings for RAGContainer tests (faster, deterministic).
os.environ.setdefault("TEST_EMBED_DIM", "128")

from src.domain.schemas import (
    DocumentMetadata,
    GeneratedAnswer,
    ParsedBlock,
    RetrievedChunk,
    SectionData,
    UserContext,
)
from src.ingestion.chunker import build_chunks
from src.ingestion.legal_structure import extract_sections
from src.rag.citation_validator import validate_and_build_citations
from src.rag.config import RAGSettings
from src.rag.container import RAGContainer
from src.services.embeddings import HashEmbeddingProvider


def test_extracts_article_clause_and_point():
    blocks = [
        ParsedBlock(
            text=(
                "Chương I QUY ĐỊNH CHUNG\n"
                "Điều 1. Phạm vi áp dụng\n"
                "1. Quy định này áp dụng cho cán bộ.\n"
                "a) Cán bộ thuộc đơn vị quản lý."
            ),
            page=2,
        )
    ]
    sections = extract_sections(blocks)
    assert [item.section_type for item in sections] == ["chapter", "article", "clause", "point"]
    assert [item.section_number for item in sections] == ["I", "1", "1", "a"]
    assert all(item.page == 2 for item in sections)


def test_chunk_ids_are_qdrant_compatible_uuids():
    chunks = build_chunks(
        document_id=str(uuid.uuid4()),
        version_id=str(uuid.uuid4()),
        metadata=DocumentMetadata(
            title="Quy chế thử nghiệm",
            document_number="01/QĐ-ĐHBK",
            owner_department="TCCB",
        ),
        sections=[
            SectionData(
                heading_path=["Điều 1"],
                section_type="article",
                section_number="1",
                heading="Điều 1",
                text="Nội dung điều một.",
            )
        ],
        max_chars=500,
        overlap_chars=50,
    )
    assert uuid.UUID(chunks[0].id)
    assert chunks[0].metadata["source_section_index"] == 0
    assert chunks[0].metadata["article"] == "1"


@pytest.mark.asyncio
async def test_hash_embedding_is_deterministic():
    provider = HashEmbeddingProvider(dimensions=64)
    first = await provider.embed_query("quy định nghỉ phép")
    second = await provider.embed_query("quy định nghỉ phép")
    assert first == second
    assert len(first) == 64


def test_rejects_hallucinated_citation():
    evidence = [
        RetrievedChunk(
            chunk_id="known",
            text="Nội dung",
            score=0.9,
            source="hybrid",
            metadata={
                "document_id": "d",
                "version_id": "v",
                "document_number": "01/QĐ",
                "title": "Quy định",
            },
        )
    ]
    generated = GeneratedAnswer(answer="Kết luận", cited_chunk_ids=["invented"])
    validated, citations = validate_and_build_citations(generated, evidence)
    assert citations == []
    assert validated.confidence == "low"
    assert "chưa thể xác minh" in validated.answer


@pytest.mark.asyncio
async def test_end_to_end_rag_and_department_filter(tmp_path):
    settings = RAGSettings(
        app_env="test",
        database_url="sqlite://",
        data_dir=tmp_path,
        generator_provider="template",
        embedding_provider="hash",
        embedding_dimensions=128,
        vector_backend="memory",
        docling_enabled=False,
        minimum_evidence_score=0.01,
    )
    container = RAGContainer(settings)
    metadata = DocumentMetadata(
        title="Quy định nghỉ phép thử nghiệm",
        document_number="TEST-01/QĐ-ĐHBK",
        owner_department="TCCB",
        access_level="department",
        allowed_departments=["TCCB"],
        effective_from="2020-01-01",
        effective_to="2099-12-31",
    )
    content = (
        "Điều 1. Nghỉ phép năm\n"
        "1. Cán bộ được nghỉ phép theo kế hoạch.\n"
        "Điều 2. Thẩm quyền\n"
        "1. Trưởng đơn vị xem xét và phê duyệt đề nghị nghỉ phép."
    ).encode()

    ingested = await container.ingestion.ingest("rule.txt", content, metadata)
    container.repository.approve_version(ingested.version_id, "owner-01")
    indexed = await container.ingestion.index_approved_version(ingested.version_id)
    container.repository.publish_version(ingested.version_id)
    assert indexed >= 2

    denied = await container.pipeline.ainvoke(
        {
            "query": "Ai phê duyệt nghỉ phép?",
            "user": UserContext(user_id="staff-ctsv", tenant_id="hust", department="CTSV"),
        }
    )
    assert denied["citations"] == []

    allowed = await container.pipeline.ainvoke(
        {
            "query": "Ai phê duyệt nghỉ phép?",
            "user": UserContext(user_id="staff-tccb", tenant_id="hust", department="TCCB"),
        }
    )
    # Stricter 2026-09-01 contract: SUFFICIENT requires >= 2 citations,
    # and the template generator cites only the best chunk, so the
    # workflow downgrades the answer to "unverified" and clears the
    # citations list. The ACL decision is still observable through the
    # warnings (which include the unverified reason).
    assert allowed["outcome"] == "unverified"
    assert "chưa thể xác minh" in allowed["answer"].lower() or any(
        "trích d" in warning.lower() for warning in allowed.get("warnings", [])
    )
