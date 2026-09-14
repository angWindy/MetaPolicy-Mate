"""Stricter evidence-gate contract enforced 2026-09-01.

Contract summary (mirrors the docstring in ``src/retrieval/evidence_gate.py``):

* SUFFICIENT requires at least 2 selected candidates. A single chunk is
  downgraded to ABSTAIN so the citation validator never sees a "thin
  evidence base" answer.
* PARTIAL still rides on a single candidate but auto-abstains when 0
  candidates are available.
* CONFLICT always escalates.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domain.schemas import (
    Candidate,
    EvidenceAction,
    Latency,
    RerankResult,
    RetrievalStatus,
    RetrievedChunk,
    UserContext,
)
from src.rag.citation_validator import (
    MIN_CITATIONS_FOR_GENERATION,
    MIN_CITATIONS_FOR_SUFFICIENT,
    validate_and_build_citations,
)
from src.rag.config import EvidenceThresholds, RAGSettings
from src.domain.schemas import GeneratedAnswer
from src.retrieval.evidence_gate import evaluate_evidence


def candidate(
    chunk_id: str,
    *,
    score: float = 0.9,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Candidate:
    document_id = document_id or f"doc-{chunk_id}"
    payload = {
        "document_number": f"01-{chunk_id}/QD",
        "title": f"Regulation {chunk_id}",
        "article": "5",
        "source_url": f"https://example.edu/{chunk_id}",
        "legal_status": "effective",
        **(metadata or {}),
    }
    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=f"version-{chunk_id}",
        content=f"Evidence {chunk_id}",
        metadata=payload,
        fusion_score=0.02,
        rerank_score=score,
    )


def result(status: RetrievalStatus, candidates: list[Candidate]) -> RerankResult:
    return RerankResult(
        status=status,
        original_query="What is the applicable rule?",
        candidates=candidates,
        latency=Latency(total_ms=1.0),
    )


def settings(**threshold_updates: Any) -> RAGSettings:
    return RAGSettings(
        app_env="test",
        evidence_thresholds_by_domain={
            "general": EvidenceThresholds(**threshold_updates),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Stricter contract: SUFFICIENT needs >=2 candidates
# ─────────────────────────────────────────────────────────────────────────────


def test_sufficient_with_1_candidate_is_downgraded_to_abstain():
    """Stricter contract: a single chunk is not enough evidence to GENERATE."""

    assessment = evaluate_evidence(
        result(RetrievalStatus.SUFFICIENT, [candidate("solo", score=0.95)]),
        settings(),
    )
    assert assessment.status is RetrievalStatus.SUFFICIENT
    # Single chunk → downgraded to ABSTAIN even though status is SUFFICIENT.
    assert assessment.decision is EvidenceAction.ABSTAIN
    assert len(assessment.selected_candidates) == 0
    assert assessment.citations == []


def test_sufficient_with_2_candidates_still_generates():
    assessment = evaluate_evidence(
        result(
            RetrievalStatus.SUFFICIENT,
            [candidate("a", score=0.95), candidate("b", score=0.85)],
        ),
        settings(),
    )
    assert assessment.status is RetrievalStatus.SUFFICIENT
    assert assessment.decision is EvidenceAction.GENERATE
    assert len(assessment.selected_candidates) == 2


# ─────────────────────────────────────────────────────────────────────────────
# PARTIAL auto-abstain when 0 candidates
# ─────────────────────────────────────────────────────────────────────────────


def test_partial_with_zero_candidates_abstains():
    assessment = evaluate_evidence(
        result(RetrievalStatus.PARTIAL, []),
        settings(),
    )
    # The reranker reported PARTIAL but there are no candidates to cite.
    # The gate must downgrade to ABSTAIN.
    assert assessment.decision is EvidenceAction.ABSTAIN
    assert assessment.citations == []


def test_partial_with_one_candidate_generates():
    assessment = evaluate_evidence(
        result(RetrievalStatus.PARTIAL, [candidate("solo", score=0.6)]),
        settings(),
    )
    assert assessment.decision is EvidenceAction.GENERATE
    assert len(assessment.selected_candidates) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Citation validator enforces minimum count
# ─────────────────────────────────────────────────────────────────────────────


def _retrieved(c: Candidate) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=c.chunk_id,
        text=c.content,
        score=c.rerank_score or 0.0,
        source="test",
        metadata={
            **c.metadata,
            "document_id": c.document_id,
            "version_id": c.version_id,
        },
    )


def test_generation_with_zero_citations_is_marked_unverified():
    """Generated answer that cites no chunks must be downgraded to unverified."""

    generated = GeneratedAnswer(answer="...", cited_chunk_ids=[])
    evidence = [_retrieved(candidate("a"))]
    validated, citations = validate_and_build_citations(generated, evidence)

    # The validator downgrades the answer when no citations exist.
    assert citations == []
    # ``mark_answer_unverified`` returns the unverified canned answer.
    assert validated.confidence == "low"


def test_minimum_citations_for_sufficient_is_strictly_higher_than_generation():
    """SUFFICIENT demands 2+ citations, but the default (PARTIAL) only needs 1."""

    assert MIN_CITATIONS_FOR_GENERATION < MIN_CITATIONS_FOR_SUFFICIENT
    assert MIN_CITATIONS_FOR_SUFFICIENT == 2
    assert MIN_CITATIONS_FOR_GENERATION == 1


def test_sufficient_path_with_one_citation_marks_unverified():
    """Even with evidence, a single citation is not enough for SUFFICIENT."""

    generated = GeneratedAnswer(
        answer="Trả lời có trích dẫn",
        cited_chunk_ids=["a"],
    )
    evidence = [
        _retrieved(candidate("a", score=0.95)),
        _retrieved(candidate("b", score=0.85)),
    ]
    validated, citations = validate_and_build_citations(
        generated,
        evidence,
        expected_min_citations=MIN_CITATIONS_FOR_SUFFICIENT,
    )
    assert citations == []
    assert validated.confidence == "low"
    # The canned "chưa thể xác minh" answer is returned.
    assert "chưa thể xác minh" in validated.answer.lower() or "trích d" in validated.answer.lower()
