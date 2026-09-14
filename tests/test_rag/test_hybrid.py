from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError
from qdrant_client.models import Filter

from src.domain.schemas import Candidate, RetrievalStatus, UserContext
from src.rag.config import RAGSettings
from src.retrieval.hybrid import (
    HybridRetriever,
    cap_chunks_per_document,
    deduplicate_candidates,
    filter_candidates_by_explicit_identifiers,
    hybrid_retrieve,
    rrf_fuse,
    weighted_rrf_fuse,
)


def test_explicit_identifier_filter_never_falls_back_to_an_unrelated_document():
    candidates = [
        {
            "text": "Quy định áp dụng chung.",
            "embedding_text": "Quy định áp dụng chung.",
            "payload": {
                "document_number": "EVAL-PUBLIC-2026",
                "title": "Quy định công khai",
            },
        }
    ]

    assert filter_candidates_by_explicit_identifiers(
        "EVAL-PUBLIC-2026 áp dụng cho ai?", candidates
    ) == candidates
    assert filter_candidates_by_explicit_identifiers(
        "EVAL-EXPIRED-2024 còn áp dụng không?", candidates
    ) == []
    assert filter_candidates_by_explicit_identifiers(
        "Quy định áp dụng cho ai?", candidates
    ) == candidates


def test_student_identifier_filter_selects_only_the_exact_table_row():
    candidates = [
        {
            "text": "20240799E | Hoàng Văn Mạnh | KỸ THUẬT VẬT LIỆU",
            "embedding_text": "Danh sách | 20240799E | Hoàng Văn Mạnh",
            "payload": {"document_number": "10714/TABLE-ĐHBK"},
        },
        {
            "text": "20240798E | Nguyễn Văn A | CƠ KHÍ",
            "embedding_text": "Danh sách | 20240798E | Nguyễn Văn A",
            "payload": {"document_number": "10714/TABLE-ĐHBK"},
        },
    ]

    assert filter_candidates_by_explicit_identifiers(
        "Mã số 20240799E học ngành gì?", candidates
    ) == [candidates[0]]


def test_document_number_filter_prefers_metadata_alias_over_cross_reference():
    candidates = [
        {
            "text": "Quy chế này viện dẫn Quyết định 5445/QĐ-ĐHBK.",
            "embedding_text": "Văn bản ngoại ngữ",
            "payload": {
                "document_number": "RAW-HUST-10728",
                "title": "10728",
            },
        },
        {
            "text": "Điều 19. Cảnh báo học tập.",
            "embedding_text": "Cảnh báo học tập",
            "payload": {
                "document_number": "RAW-HUST-5445",
                "title": "5445",
            },
        },
    ]

    assert filter_candidates_by_explicit_identifiers(
        "5445/QĐ-ĐHBK quy định cảnh báo học tập thế nào?", candidates
    ) == [candidates[1]]

    assert filter_candidates_by_explicit_identifiers(
        "Theo QĐ 5445, mức điểm đạt tối thiểu là gì?", candidates
    ) == [candidates[1]]


def test_exact_identifier_rank_prioritizes_identifier_and_query_terms():
    score = HybridRetriever._exact_identifier_rank(
        "Mã số 20240799E học ngành gì?",
        {
            "text": "20240799E | Hoàng Văn Mạnh | Kỹ thuật vật liệu",
            "embedding_text": "Danh sách học viên Kỹ thuật vật liệu",
            "payload": {},
        },
    )

    assert score >= 0.9


def make_candidate(
    chunk_id: str,
    *,
    document_id: str | None = None,
    dense_rank: int | None = None,
    sparse_rank: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        version_id=f"version-{document_id or chunk_id}",
        content=f"Content for {chunk_id}",
        metadata={"tenant_id": "tenant-a", **(metadata or {})},
        dense_rank=dense_rank,
        sparse_rank=sparse_rank,
        fusion_score=0.0,
        rerank_score=None,
    )


class FakeHybridLegs:
    def __init__(
        self,
        *,
        dense: list[Candidate] | None = None,
        sparse: list[Candidate] | None = None,
        dense_delay: float = 0.0,
        sparse_delay: float = 0.0,
        dense_error: Exception | None = None,
        sparse_error: Exception | None = None,
    ):
        self.results = {"dense": dense or [], "sparse": sparse or []}
        self.delays = {"dense": dense_delay, "sparse": sparse_delay}
        self.errors = {"dense": dense_error, "sparse": sparse_error}
        self.calls: dict[str, tuple[str, Filter, int, str]] = {}
        self.active = 0
        self.max_active = 0

    async def _retrieve(
        self,
        name: str,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]:
        self.calls[name] = (query, access_filter, limit, index_version)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delays[name])
            if self.errors[name] is not None:
                raise self.errors[name]
            return self.results[name]
        finally:
            self.active -= 1

    async def dense_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]:
        return await self._retrieve(
            "dense", query, access_filter, limit, index_version
        )

    async def sparse_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]:
        return await self._retrieve(
            "sparse", query, access_filter, limit, index_version
        )


def settings(**overrides: Any) -> RAGSettings:
    values = {
        "fused_limit": 50,
        "retrieval_leg_timeout_seconds": 1.0,
        **overrides,
    }
    return RAGSettings(**values)


def user_context() -> UserContext:
    return UserContext(
        user_id="user-a",
        tenant_id="tenant-a",
        department="TCCB",
        roles={"staff"},
        clearance_level="internal",
    )


def build_legacy_retriever(alpha: float = 0.3) -> HybridRetriever:
    return HybridRetriever(
        settings=RAGSettings(rrf_k=60, rrf_alpha=alpha),
        repository=None,  # type: ignore[arg-type]
        embeddings=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
    )


def test_hybrid_configuration_defaults_and_safe_bounds():
    defaults = RAGSettings()
    assert defaults.fused_limit == 60
    assert defaults.max_chunks_per_document == 4
    with pytest.raises(ValidationError):
        RAGSettings(fused_limit=49)
    with pytest.raises(ValidationError):
        RAGSettings(fused_limit=101)


def test_weighted_rrf_is_available_but_balanced_rrf_remains_default():
    dense = [make_candidate("dense-only", dense_rank=1)]
    sparse = [make_candidate("sparse-only", sparse_rank=1)]

    balanced = rrf_fuse(dense, sparse, rrf_k=60)
    weighted = weighted_rrf_fuse(
        dense,
        sparse,
        dense_weight=0.3,
        sparse_weight=0.7,
        rrf_k=60,
    )

    assert balanced[0].fusion_score == pytest.approx(balanced[1].fusion_score)
    assert weighted[0].chunk_id == "sparse-only"


def test_legacy_weighted_rrf_contract_is_preserved():
    retriever = build_legacy_retriever(alpha=0.3)
    fused, sources = retriever._weighted_rrf(
        semantic_results=[("dense-only", 0.9, {}), ("both", 0.8, {})],
        keyword_results=[("keyword-only", 5.0), ("both", 4.0)],
    )
    assert fused["dense-only"] == pytest.approx(0.3 / 61)
    assert fused["keyword-only"] == pytest.approx(0.7 / 61)
    assert fused["both"] == pytest.approx(1.0 / 62)
    assert sources["both"] == {"semantic", "keyword"}


def test_local_bm25_is_an_independent_lexical_fusion_leg():
    retriever = build_legacy_retriever(alpha=0.3)
    fused, sources = retriever._weighted_rrf_with_local_bm25(
        semantic_results=[("dense-only", 0.9, {})],
        sparse_results=[("sparse-only", 0.8, {})],
        bm25_results=[("exact-table-row", 12.0)],
    )

    assert set(fused) == {"dense-only", "sparse-only", "exact-table-row"}
    assert sources["dense-only"] == {"semantic"}
    assert sources["sparse-only"] == {"sparse"}
    assert sources["exact-table-row"] == {"bm25"}


def test_candidate_in_both_lexical_legs_receives_combined_support():
    retriever = build_legacy_retriever(alpha=0.3)
    fused, sources = retriever._weighted_rrf_with_local_bm25(
        semantic_results=[],
        sparse_results=[("shared", 0.8, {}), ("sparse-only", 0.7, {})],
        bm25_results=[("shared", 10.0), ("bm25-only", 9.0)],
    )

    assert fused["shared"] > fused["sparse-only"]
    assert fused["shared"] > fused["bm25-only"]
    assert sources["shared"] == {"sparse", "bm25"}


@pytest.mark.parametrize("alpha", [0.2, 0.3, 0.4])
def test_rrf_alpha_accepts_tuning_range(alpha: float):
    assert RAGSettings(rrf_alpha=alpha).rrf_alpha == alpha


@pytest.mark.parametrize("alpha", [0.19, 0.41])
def test_rrf_alpha_rejects_values_outside_tuning_range(alpha: float):
    with pytest.raises(ValidationError):
        RAGSettings(rrf_alpha=alpha)


@pytest.mark.asyncio
async def test_hybrid_retrieve_dense_only_fallback():
    legs = FakeHybridLegs(dense=[make_candidate("dense", dense_rank=1)])
    result = await hybrid_retrieve(
        "quy định nghỉ phép",
        user_context(),
        "index-v1",
        dense_retriever=legs,
        sparse_retriever=legs,
        settings=settings(),
    )
    assert result.status == RetrievalStatus.PARTIAL
    assert [candidate.chunk_id for candidate in result.candidates] == ["dense"]
    assert result.candidates[0].dense_rank == 1
    assert "Sparse retrieval returned no candidates." in result.warnings


@pytest.mark.asyncio
async def test_hybrid_retrieve_sparse_only_fallback():
    legs = FakeHybridLegs(sparse=[make_candidate("sparse", sparse_rank=1)])
    result = await hybrid_retrieve(
        "QT-TC-003",
        user_context(),
        "index-v1",
        dense_retriever=legs,
        sparse_retriever=legs,
        settings=settings(),
    )
    assert result.status == RetrievalStatus.PARTIAL
    assert [candidate.chunk_id for candidate in result.candidates] == ["sparse"]
    assert result.candidates[0].sparse_rank == 1


@pytest.mark.asyncio
async def test_mixed_query_runs_legs_concurrently_and_passes_access_filter():
    legs = FakeHybridLegs(
        dense=[make_candidate("semantic", dense_rank=1)],
        sparse=[make_candidate("QT-TC-003", sparse_rank=1)],
        dense_delay=0.02,
        sparse_delay=0.02,
    )
    result = await hybrid_retrieve(
        "QT-TC-003 quy định việc gì",
        user_context(),
        "index-v1",
        dense_retriever=legs,
        sparse_retriever=legs,
        settings=settings(),
    )
    assert result.status == RetrievalStatus.SUFFICIENT
    assert legs.max_active == 2
    assert set(legs.calls) == {"dense", "sparse"}
    assert all(call[2] == 50 for call in legs.calls.values())
    assert all(call[3] == "index-v1" for call in legs.calls.values())
    assert all("tenant-a" in call[1].model_dump_json() for call in legs.calls.values())
    assert all(
        candidate.metadata["tenant_id"] == "tenant-a"
        for candidate in result.candidates
    )


@pytest.mark.asyncio
async def test_one_leg_timeout_falls_back_without_leaking_exception_text():
    legs = FakeHybridLegs(
        dense=[make_candidate("late", dense_rank=1)],
        sparse=[make_candidate("available", sparse_rank=1)],
        dense_delay=0.05,
    )
    result = await hybrid_retrieve(
        "Mẫu 04",
        user_context(),
        "index-v1",
        dense_retriever=legs,
        sparse_retriever=legs,
        settings=settings(retrieval_leg_timeout_seconds=0.01),
    )
    assert result.status == RetrievalStatus.PARTIAL
    assert [candidate.chunk_id for candidate in result.candidates] == ["available"]
    assert result.warnings == ["Dense retrieval timed out."]


@pytest.mark.asyncio
async def test_both_legs_failed_returns_not_found():
    legs = FakeHybridLegs(
        dense_error=RuntimeError("sensitive dense details"),
        sparse_error=RuntimeError("sensitive sparse details"),
    )
    result = await hybrid_retrieve(
        "quy định học phí",
        user_context(),
        "index-v1",
        dense_retriever=legs,
        sparse_retriever=legs,
        settings=settings(),
    )
    assert result.status == RetrievalStatus.NOT_FOUND
    assert result.candidates == []
    assert result.warnings == [
        "Dense retrieval failed (RuntimeError).",
        "Sparse retrieval failed (RuntimeError).",
    ]


def test_duplicate_chunk_is_merged_by_chunk_id():
    dense = make_candidate(
        "shared", dense_rank=2, metadata={"dense_score": 0.93}
    )
    sparse = make_candidate(
        "shared", sparse_rank=1, metadata={"sparse_score": 8.4}
    )
    fused = rrf_fuse([dense, dense], [sparse], rrf_k=60)
    assert len(fused) == 1
    assert fused[0].dense_rank == 2
    assert fused[0].sparse_rank == 1
    assert fused[0].metadata["retrieval_sources"] == ["dense", "sparse"]
    assert fused[0].metadata["dense_score"] == 0.93
    assert fused[0].metadata["sparse_score"] == 8.4
    assert fused[0].fusion_score == pytest.approx(1 / 62 + 1 / 61)
    assert len(deduplicate_candidates([dense, dense])) == 1


def test_document_dominance_is_capped_at_four_chunks():
    dominant = [
        make_candidate(f"dominant-{rank}", document_id="doc-dominant", dense_rank=rank)
        for rank in range(1, 11)
    ]
    diverse = [
        make_candidate(f"diverse-{rank}", document_id=f"doc-{rank}", dense_rank=10 + rank)
        for rank in range(1, 7)
    ]
    selected = cap_chunks_per_document(
        rrf_fuse([*dominant, *diverse], []),
        limit=10,
        max_chunks_per_document=4,
    )
    assert len(selected) == 10
    assert sum(item.document_id == "doc-dominant" for item in selected) == 4
    assert len({item.document_id for item in selected}) == 7


def test_synthetic_hybrid_recall_baseline_at_50_and_100():
    dense_ids = [f"dense-{rank}" for rank in range(1, 101)]
    sparse_ids = [f"sparse-{rank}" for rank in range(1, 101)]
    dense_ids[4] = "relevant-a"
    dense_ids[79] = "relevant-b"
    sparse_ids[9] = "relevant-b"
    sparse_ids[44] = "relevant-c"
    dense = [
        make_candidate(chunk_id, dense_rank=rank)
        for rank, chunk_id in enumerate(dense_ids, start=1)
    ]
    sparse = [
        make_candidate(chunk_id, sparse_rank=rank)
        for rank, chunk_id in enumerate(sparse_ids, start=1)
    ]
    fused = rrf_fuse(dense, sparse)
    relevant = {"relevant-a", "relevant-b", "relevant-c"}

    def recall(candidates: list[Candidate], cutoff: int) -> float:
        returned = {candidate.chunk_id for candidate in candidates[:cutoff]}
        return len(returned & relevant) / len(relevant)

    assert recall(dense, 50) == pytest.approx(1 / 3)
    assert recall(dense, 100) == pytest.approx(2 / 3)
    assert recall(sparse, 50) == pytest.approx(2 / 3)
    assert recall(sparse, 100) == pytest.approx(2 / 3)
    assert recall(fused, 50) == pytest.approx(2 / 3)
    assert recall(fused, 100) == pytest.approx(1.0)
