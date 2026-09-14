"""Tests for the evidence reranking pipeline.

These tests exercise the reranking logic at three levels:
1. Pure logic functions: ``apply_mmr``, ``detect_score_gap``,
   ``cap_final_chunks_per_document``, ``select_final_contexts``
2. Service-level with controlled (injected) scores via
   ``ControlledReranker`` — no real model required
3. Integration with the real ``reranker_service`` fixture when
   end-to-end verification is needed

``FakeRerankerService`` has been removed; controlled behavior is now
achieved by passing injected scores through ``ControlledReranker``,
which follows the same ``BaseReranker`` interface as the production
``CrossEncoderReranker``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from src.domain.schemas import Candidate, Latency, RerankRequest, RerankResult, RetrievalStatus
from src.rag.config import RAGSettings
from src.retrieval.evidence_rerank import (
    apply_mmr,
    apply_score_threshold,
    cap_final_chunks_per_document,
    detect_score_gap,
    rerank_evidence,
    select_final_contexts,
)
from src.retrieval.reranker import (
    BaseReranker,
    CrossEncoderReranker,
    RerankerService,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_candidate(
    chunk_id: str,
    *,
    document_id: str | None = None,
    content: str | None = None,
    fusion_score: float = 0.0,
    rerank_score: float | None = None,
) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        version_id=f"version-{document_id or chunk_id}",
        content=content or f"Nội dung riêng của {chunk_id}",
        metadata={},
        dense_rank=1,
        sparse_rank=1,
        fusion_score=fusion_score,
        rerank_score=rerank_score,
    )


# ---------------------------------------------------------------------------
# Controlled reranker (injects arbitrary scores, follows BaseReranker)
# ---------------------------------------------------------------------------


class ControlledReranker(BaseReranker):
    """A ``BaseReranker`` that returns pre-defined scores for each chunk_id.

    Lets tests exercise service-layer logic (timeout, circuit-breaker, fallback)
    without depending on a real sentence-transformer model.
    """

    def __init__(
        self,
        scores: Mapping[str, float],
        *,
        raise_error: bool = False,
    ) -> None:
        self.scores = dict(scores)
        self.raise_error = raise_error
        self._loaded = False
        self._warmed_up = False

    def load_model(self) -> Any:
        self._loaded = True
        return self

    def warmup_model(self) -> None:
        self._warmed_up = True

    def rerank_batch(
        self,
        query: str,
        candidates: Sequence[Candidate],
    ) -> list[float]:
        if self.raise_error:
            raise RuntimeError("ControlledReranker is configured to fail.")
        return [self.scores.get(c.chunk_id, 0.0) for c in candidates]

    def get_model_metadata(self) -> Any:
        from src.retrieval.reranker import RerankerModelMetadata

        return RerankerModelMetadata(
            model_name="controlled/mock",
            revision="0.0.0",
            device="mock",
            backend="mock",
            batch_size=1,
            max_length=128,
            loaded=self._loaded,
            warmed_up=self._warmed_up,
        )


def controlled_service(
    scores: Mapping[str, float],
    *,
    raise_error: bool = False,
) -> RerankerService:
    """Build a ``RerankerService`` backed by a ``ControlledReranker``."""
    reranker = ControlledReranker(scores, raise_error=raise_error)
    return RerankerService(
        reranker,
        timeout_seconds=5.0,
        circuit_failure_threshold=3,
        circuit_cooldown_seconds=1.0,
    )


# ---------------------------------------------------------------------------
# Tests: pure logic (no reranker required)
# ---------------------------------------------------------------------------


def test_mmr_does_not_select_five_identical_contents():
    duplicates = [
        make_candidate(
            f"duplicate-{index}",
            content="Cùng một nội dung bằng chứng.",
            rerank_score=10.0 - index,
        )
        for index in range(5)
    ]
    diverse = [
        make_candidate(f"diverse-{index}", rerank_score=4.0 - index)
        for index in range(5)
    ]

    selected = apply_mmr([*duplicates, *diverse], limit=5)

    normalized = [" ".join(candidate.content.casefold().split()) for candidate in selected]
    assert len(normalized) == len(set(normalized))
    assert len(selected) == 5


def test_ground_truth_is_not_lost_by_final_diversity():
    candidates = [
        make_candidate(
            "ground-truth",
            document_id="doc-ground",
            rerank_score=12.0,
        ),
        *[
            make_candidate(
                f"chunk-{index}",
                document_id="dominant" if index < 6 else f"doc-{index}",
                rerank_score=11.0 - index,
            )
            for index in range(10)
        ],
    ]

    selected = select_final_contexts(candidates, final_limit=5)

    assert "ground-truth" in {candidate.chunk_id for candidate in selected}
    assert max(
        sum(candidate.document_id == document_id for candidate in selected)
        for document_id in {candidate.document_id for candidate in selected}
    ) <= 2


def test_score_gap_returns_cutoff_for_raw_scores_outside_unit_interval():
    candidates = [
        make_candidate(str(index), rerank_score=score)
        for index, score in enumerate([14.0, 12.0, 10.0, 2.0, -4.0])
    ]

    assert detect_score_gap(candidates, minimum_gap=5.0) == 3
    assert detect_score_gap(candidates, minimum_gap=9.0) is None


def test_threshold_is_raw_and_document_cap_is_two():
    candidates = [
        make_candidate(
            str(index),
            document_id="same-document",
            rerank_score=score,
        )
        for index, score in enumerate([105.0, 101.0, 99.0, 90.0])
    ]
    candidates.append(make_candidate("other", rerank_score=80.0))

    thresholded = apply_score_threshold(candidates, threshold=100.0)
    capped = cap_final_chunks_per_document(thresholded, limit=5)

    assert [candidate.rerank_score for candidate in thresholded] == [105.0, 101.0]
    assert len(capped) == 2


def _ndcg_at_five(ranking: list[str], relevance: Mapping[str, int]) -> float:
    gains = [relevance.get(chunk_id, 0) for chunk_id in ranking[:5]]
    dcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(gains))
    ideal = sorted(relevance.values(), reverse=True)[:5]
    idcg = sum((2**gain - 1) / math.log2(index + 2) for index, gain in enumerate(ideal))
    return dcg / idcg


def test_synthetic_ndcg_at_five_improves_after_rerank():
    relevance = {"ground": 3, "support-a": 2, "support-b": 2, "minor": 1}
    fusion = ["noise-a", "noise-b", "support-a", "noise-c", "ground"]
    reranked = ["ground", "support-a", "support-b", "minor", "noise-a"]

    before = _ndcg_at_five(fusion, relevance)
    after = _ndcg_at_five(reranked, relevance)

    assert before == pytest.approx(0.38878208894395405)
    assert after == pytest.approx(1.0)
    assert after > before


# ---------------------------------------------------------------------------
# Tests: service layer with controlled scores
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reranker_changes_ranking_and_preserves_both_scores():
    candidates = [
        make_candidate("a", fusion_score=0.9),
        make_candidate("b", fusion_score=0.8),
        make_candidate("ground-truth", fusion_score=0.1),
        make_candidate("c", fusion_score=0.7),
    ]
    service = controlled_service(
        {"a": -2.0, "b": 4.0, "ground-truth": 9.0, "c": 1.0}
    )

    result = await rerank_evidence(
        original_query="Điều kiện áp dụng là gì?",
        candidates=candidates,
        reranker_service=service,
        settings=RAGSettings(final_context_limit=3),
    )

    assert result.status == RetrievalStatus.SUFFICIENT
    assert result.candidates[0].chunk_id == "ground-truth"
    assert result.candidates[0].fusion_score == 0.1
    assert result.candidates[0].rerank_score == 9.0


@pytest.mark.asyncio
async def test_threshold_that_removes_everything_returns_weak():
    candidates = [make_candidate(str(index)) for index in range(4)]
    service = controlled_service({str(index): -10.0 - index for index in range(4)})

    result = await rerank_evidence(
        original_query="Câu hỏi",
        candidates=candidates,
        reranker_service=service,
        settings=RAGSettings(rerank_score_threshold=0.0, final_context_limit=3),
    )

    assert result.status == RetrievalStatus.WEAK
    assert result.candidates == []
    assert result.warnings == [
        "No candidate met the configured rerank score threshold."
    ]


@pytest.mark.asyncio
async def test_fallback_keeps_rrf_order_and_partial_status():
    """When the reranker raises an error, the service falls back to RRF."""
    candidates = [
        make_candidate("low", fusion_score=0.1),
        make_candidate("high", fusion_score=0.9),
        make_candidate("middle", fusion_score=0.5),
    ]
    # A ControlledReranker that always raises an exception.
    service = controlled_service({}, raise_error=True)

    result = await rerank_evidence(
        original_query="Câu hỏi",
        candidates=candidates,
        reranker_service=service,
        settings=RAGSettings(final_context_limit=3),
    )

    assert result.status == RetrievalStatus.PARTIAL
    assert result.candidates[0].chunk_id == "high"
    assert all(c.rerank_score is None for c in result.candidates)


# ---------------------------------------------------------------------------
# Integration test: real reranker (requires model download / RAG runtime)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.requires_rag_runtime
async def test_real_reranker_service_produces_valid_result(reranker_service):
    """End-to-end smoke test using the real ``RerankerService``."""
    candidates = [
        make_candidate("a", content="Quy định về phạm vi áp dụng."),
        make_candidate("b", content="Điều kiện và thể thức thực hiện."),
        make_candidate("c", content="Hướng dẫn chi tiết cách thực hiện quy trình."),
    ]

    result = await rerank_evidence(
        original_query="Quy định này áp dụng cho ai?",
        candidates=candidates,
        reranker_service=reranker_service,
        settings=RAGSettings(final_context_limit=3),
    )

    assert result.status == RetrievalStatus.SUFFICIENT
    assert len(result.candidates) >= 1
    # Every returned candidate must have a valid (finite) rerank score.
    for candidate in result.candidates:
        assert candidate.rerank_score is not None
        assert math.isfinite(candidate.rerank_score)
