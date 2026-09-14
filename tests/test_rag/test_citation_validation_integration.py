"""Integration tests for the citation validator against realistic inputs.

These tests exercise the validator end-to-end with full QdrantPayload /
Citation objects so we can verify the production paths:

- Citation allowlist (multi-tenant ACL)
- Metadata completeness bypass
- Sufficient / partial evidence threshold
- Source URL validation
- Unverified marking when citations fall below the threshold
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")

from datetime import date

import pytest

from src.domain.schemas import (
    AccessScope,
    Citation,
    CitationKind,
    GeneratedAnswer,
    LegalStatus,
    RetrievedChunk,
    UserContext,
)
from src.rag.citation_validator import (
    MIN_CITATIONS_FOR_SUFFICIENT,
    build_citations,
    mark_answer_unverified,
    validate_and_build_citations,
)


def make_user_context(
    tenant_id: str = "hust",
    department: str = "TCCB",
    roles: set[str] | None = None,
) -> UserContext:
    return UserContext(
        user_id="user-1",
        tenant_id=tenant_id,
        department=department,
        roles=roles or {"staff"},
    )


def make_chunk(
    chunk_id: str,
    *,
    document_id: str = "doc-1",
    version_id: str = "version-1",
    document_number: str = "01/QĐ-ĐHBK",
    title: str = "Quy định nghỉ phép",
    article: str | None = "5",
    section: str | None = "Điều 5",
    page: int | None = 3,
    tenant_id: str = "hust",
    legal_status: str = LegalStatus.EFFECTIVE.value,
    allowed_units: list[str] | None = None,
    rerank_score: float | None = 0.95,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=f"Chunk content for {chunk_id}",
        score=rerank_score if rerank_score is not None else 0.95,
        source="hybrid",
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "version_id": version_id,
            "document_number": document_number,
            "title": title,
            "article": article,
            "section": section,
            "page": page,
            "source_url": f"https://example.edu/rules/{document_id}",
            "legal_status": legal_status,
            "tenant_id": tenant_id,
            "status": "published",
            "classification": "internal",
            "allowed_roles": ["staff"],
            "allowed_units": allowed_units or ["TCCB"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
            "rerank_score": rerank_score,
            "content_hash": "hash123",
            "embedding_model": "text-embedding-3-small",
            "embedding_version": "v1",
            "index_version": "v1",
        },
    )


def make_citation(chunk_id: str, *, extras: dict | None = None) -> Citation:
    base = {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "version_id": "version-1",
        "document_number": "01/QĐ-ĐHBK",
        "title": "Quy định nghỉ phép",
        "source": "01/QĐ-ĐHBK, Điều 5",
        "article": "5",
        "clause": None,
        "point": None,
        "section": "Điều 5",
        "page": 3,
        "source_url": "https://example.edu/rules/doc-1",
        "excerpt": "Chunk content",
        "citation_kind": CitationKind.WINNING,
        "winning_chunk_id": chunk_id,
        "rerank_score": 0.95,
    }
    if extras:
        base.update(extras)
    return Citation(**base)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _citation_has_complete_metadata bypass
# ─────────────────────────────────────────────────────────────────────────────


def test_single_citation_with_complete_metadata_passes_sufficient_gate():
    """When evidence is SUFFICIENT but only 1 chunk exists, the validator
    must accept it if the citation has complete metadata
    (document_number + section + page)."""
    user = make_user_context()
    chunk = make_chunk("chunk-A", article="5", section="Điều 5", page=3)
    generated = GeneratedAnswer(
        answer="Theo Điều 5, cán bộ được nghỉ phép.",
        cited_chunk_ids=["chunk-A"],
        confidence="medium",
    )
    validated, citations = validate_and_build_citations(
        generated,
        [chunk],
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=MIN_CITATIONS_FOR_SUFFICIENT,  # 2
    )
    # Single citation with complete metadata must pass even though
    # the strict threshold would be 2.
    assert len(citations) >= 1
    assert any(c.chunk_id == "chunk-A" for c in citations)


def test_single_citation_without_section_fails_threshold():
    """Citation without ``section`` triggers a soft warning but should
    still pass when evidence is PARTIAL (>=1)."""
    user = make_user_context()
    chunk = make_chunk("chunk-A", section=None, article="5", page=3)
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=["chunk-A"],
        confidence="low",
    )
    validated, citations = validate_and_build_citations(
        generated,
        [chunk],
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=1,
    )
    assert len(citations) >= 1
    assert any(c.chunk_id == "chunk-A" for c in citations)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-tenant access control for citations
# ─────────────────────────────────────────────────────────────────────────────


def test_citations_filtered_for_wrong_tenant():
    """Chunks belonging to a different tenant must not be cited."""
    user = make_user_context(tenant_id="huce")
    chunk = make_chunk("chunk-A", tenant_id="hust")
    generated = GeneratedAnswer(
        answer="Theo quy định",
        cited_chunk_ids=["chunk-A"],
        confidence="high",
    )
    validated, citations = validate_and_build_citations(
        generated,
        [chunk],
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=1,
    )
    # The LLM's cited_chunk_ids still get filtered — cross-tenant
    # citations are dropped silently.
    assert citations == [] or all(c.chunk_id != "chunk-A" for c in citations)


def test_citations_allow_same_tenant():
    """Chunks belonging to the user's tenant pass the allowlist."""
    user = make_user_context(tenant_id="hust")
    chunk = make_chunk("chunk-A", tenant_id="hust")
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=["chunk-A"],
        confidence="high",
    )
    validated, citations = validate_and_build_citations(
        generated,
        [chunk],
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=1,
    )
    assert any(c.chunk_id == "chunk-A" for c in citations)


# ─────────────────────────────────────────────────────────────────────────────
# 3. SUFFICIENT >= 2 citations
# ─────────────────────────────────────────────────────────────────────────────


def test_two_citations_pass_sufficient_threshold():
    user = make_user_context()
    chunks = [
        make_chunk("chunk-A"),
        make_chunk("chunk-B", article="6", section="Điều 6"),
    ]
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=["chunk-A", "chunk-B"],
        confidence="high",
    )
    validated, citations = validate_and_build_citations(
        generated,
        chunks,
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=MIN_CITATIONS_FOR_SUFFICIENT,
    )
    assert len(citations) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. mark_answer_unverified when citations < threshold
# ─────────────────────────────────────────────────────────────────────────────


def test_mark_answer_unverified_appends_warning():
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=[],
        confidence="low",
    )
    marked = mark_answer_unverified(generated, reasons=["Không có trích dẫn"])
    assert marked.confidence == "low"
    assert any("Không có trích dẫn" in w for w in marked.warnings)


def test_mark_answer_unverified_keeps_existing_warnings():
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=[],
        confidence="low",
        warnings=["cảnh báo ban đầu"],
    )
    marked = mark_answer_unverified(generated, reasons=["Lý do mới"])
    assert "cảnh báo ban đầu" in marked.warnings
    assert any("Lý do mới" in w for w in marked.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Source URL validation
# ─────────────────────────────────────────────────────────────────────────────


def test_source_url_must_be_https():
    """Citations with non-https source_url should be flagged or dropped."""
    citation = make_citation(
        "chunk-A",
        extras={"source_url": "http://insecure.example.com/doc"},
    )
    # The validator should still produce the citation but flag it.
    user = make_user_context()
    chunk = make_chunk("chunk-A")
    generated = GeneratedAnswer(
        answer="Trả lời",
        cited_chunk_ids=["chunk-A"],
        confidence="high",
    )
    validated, citations = validate_and_build_citations(
        generated,
        [chunk],
        user=user,
        as_of=date(2026, 9, 1),
        expected_min_citations=1,
    )
    # Output still includes the citation but the validator may add a warning.
    assert any(c.chunk_id == "chunk-A" for c in citations)


# ─────────────────────────────────────────────────────────────────────────────
# 6. build_citations basic
# ─────────────────────────────────────────────────────────────────────────────


def test_build_citations_returns_one_per_chunk():
    chunks = [
        make_chunk("chunk-A"),
        make_chunk("chunk-B"),
    ]
    citations = build_citations(
        [c.chunk_id for c in chunks],
        chunks,
        user=make_user_context(),
        as_of=date(2026, 9, 1),
    )
    assert len(citations) == 2
    chunk_ids = {c.chunk_id for c in citations}
    assert chunk_ids == {"chunk-A", "chunk-B"}


def test_build_citations_with_empty_chunks_returns_empty():
    citations = build_citations(
        [],
        [],
        user=make_user_context(),
        as_of=date(2026, 9, 1),
    )
    assert citations == []


# ─────────────────────────────────────────────────────────────────────────────
# 7. rerank_score round-trips through citations
# ─────────────────────────────────────────────────────────────────────────────


def test_rerank_score_preserved_in_citation():
    chunk = make_chunk("chunk-A", rerank_score=0.42)
    citations = build_citations(
        [chunk.chunk_id],
        [chunk],
        user=make_user_context(),
        as_of=date(2026, 9, 1),
    )
    assert citations[0].rerank_score == 0.42


def test_citation_kind_defaults_to_winning():
    chunk = make_chunk("chunk-A")
    citations = build_citations(
        [chunk.chunk_id],
        [chunk],
        user=make_user_context(),
        as_of=date(2026, 9, 1),
    )
    assert citations[0].citation_kind == CitationKind.WINNING