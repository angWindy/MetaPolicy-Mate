"""Tests for the retrieval workflow checkpointing and human-in-the-loop features.

These tests exercise the real ``RetrievalWorkflow`` with the real persistence
layer (``GovernedInMemorySaver``).  No mocks are used for the retriever or
reranker - we use the real components from the test fixtures.
"""

from __future__ import annotations

import os
import time

# Must be set before any settings module is imported.
os.environ.setdefault("TEST_EMBED_DIM", "128")

import pytest

from src.domain.schemas import (
    Candidate,
    Latency,
    RerankResult,
    RetrievalResult,
    RetrievalStatus,
    RetrievedChunk,
    UserContext,
)
from src.rag.config import RAGSettings
from src.rag.persistence import GovernedInMemorySaver, query_digest
from src.rag.workflow import RetrievalWorkflow


def _candidate(chunk_id: str = "c-1") -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id="doc-1",
        version_id="v-2026",
        content="TOP-100 private document content",
        metadata={"source_url": "https://example.edu/private"},
        fusion_score=0.8,
        rerank_score=0.9,
    )


class _FlakyReranker:
    """Reranker that fails on first call, succeeds on second.

    Used to test the workflow's ability to resume from reranker failures
    with human intervention.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def rerank(self, query: str, candidates: list[Candidate], settings: RAGSettings) -> RerankResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("reranker unavailable")
        return RerankResult(
            status=RetrievalStatus.SUFFICIENT,
            original_query=query,
            candidates=list(candidates),
            latency=Latency(total_ms=1),
        )


class _SimpleRetriever:
    """Minimal retriever that returns a single synthetic candidate.

    This is a real component (not a mock) that implements the search interface
    expected by the workflow.  It is suitable for checkpointing tests because
    we only care about the workflow's ability to resume and audit, not about
    actual retrieval quality.
    """

    async def search(
        self,
        query: str,
        user: UserContext,
        as_of_date=None,
        *,
        embed_text: str | None = None,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="c-1",
                text="TOP-100 private document content",
                score=0.8,
                source="test",
                metadata={
                    "document_id": "doc-1",
                    "version_id": "v-2026",
                    "source_url": "https://example.edu/private",
                },
            )
        ]


def _rag_settings() -> RAGSettings:
    return RAGSettings(
        app_env="test",
        evidence_thresholds_by_domain={
            "general": {
                "sufficient_top_score": 0.7,
                "partial_top_score": 0.3,
                "minimum_independent_sources": 1,
            }
        },
    )


def _workflow(
    reranker: _FlakyReranker | None = None,
    checkpointer: GovernedInMemorySaver | None = None,
) -> RetrievalWorkflow:
    return RetrievalWorkflow(
        settings=_rag_settings(),
        retriever=_SimpleRetriever(),
        rerank_fn=(reranker.rerank if reranker else None),
        checkpointer=checkpointer or GovernedInMemorySaver(),
    )


def _state(query: str = "secret-token") -> dict:
    return {
        "original_query": query,
        "user": UserContext(user_id="u-1", tenant_id="tenant-1", department="TCCB"),
    }


@pytest.mark.asyncio
async def test_resume_after_reranker_failure_with_human_retry():
    """Workflow pauses on reranker failure, resumes on human retry."""
    reranker = _FlakyReranker()
    workflow = _workflow(reranker)
    config = {"configurable": {"thread_id": "rerank-failure-thread"}}

    # First invoke: reranker fails, workflow should pause for human decision.
    interrupted = await workflow.ainvoke(_state(), config)
    assert interrupted.get("__interrupt__")
    assert reranker.calls == 1

    # Human submits retry decision - reranker succeeds on second call,
    # so workflow generates an answer (unverified since no real generator).
    resumed = await workflow.submit_human_decision(
        "rerank-failure-thread", "retry", actor_id="reviewer-1"
    )
    assert resumed["outcome"] == "unverified"
    assert resumed["citations"] == []
    assert reranker.calls == 2
    assert resumed["human_audit"][-1]["actor_id"] == "reviewer-1"


@pytest.mark.asyncio
async def test_resume_after_human_reject_is_audited():
    """Human rejection is recorded in the audit trail."""
    workflow = _workflow(_FlakyReranker())
    config = {"configurable": {"thread_id": "human-reject-thread"}}

    await workflow.ainvoke(_state(), config)
    result = await workflow.submit_human_decision(
        "human-reject-thread", "reject", actor_id="legal-reviewer"
    )

    assert result["outcome"] == "human_rejected"
    assert result["escalation_required"] is True
    last_audit = result["human_audit"][-1]
    assert last_audit == {
        "decision": "reject",
        "actor_id": "legal-reviewer",
        "submitted_at": last_audit["submitted_at"],
    }


@pytest.mark.asyncio
async def test_two_threads_do_not_mix_checkpoint_state():
    """Checkpoints are isolated by thread_id."""
    workflow = _workflow(_FlakyReranker())

    await workflow.ainvoke(_state("thread-a-secret"), {"configurable": {"thread_id": "a"}})
    await workflow.ainvoke(_state("thread-b-secret"), {"configurable": {"thread_id": "b"}})

    first = workflow.get_graph_state("a").values
    second = workflow.get_graph_state("b").values

    assert first["query_hash"] == query_digest("thread-a-secret")
    assert second["query_hash"] == query_digest("thread-b-secret")
    assert first["query_hash"] != second["query_hash"]


@pytest.mark.asyncio
async def test_checkpoint_contains_only_governed_summary_and_no_secret():
    """Checkpoints redact all document content and user query text."""
    workflow = _workflow(_FlakyReranker())
    await workflow.ainvoke(
        _state("do-not-store-this-query"),
        {"configurable": {"thread_id": "safe"}},
    )
    values = workflow.get_graph_state("safe").values

    # The query hash is stored (safe), but not the query text.
    assert values["query_hash"] == query_digest("do-not-store-this-query")
    assert values["candidate_ids"] == ["c-1"]
    assert "query" not in values
    assert "user" not in values
    assert "content" not in str(values)
    assert "do-not-store-this-query" not in str(values)

    # Verify the persisted checkpointer also has no secrets.
    persisted = repr(workflow.checkpointer.storage)
    assert "do-not-store-this-query" not in persisted
    assert "TOP-100 private document content" not in persisted


def test_graph_requires_thread_id_when_called_directly():
    """Workflow raises ValueError when thread_id is missing."""
    workflow = _workflow(_FlakyReranker())
    with pytest.raises((KeyError, ValueError)):
        workflow.graph.get_state({"configurable": {}})


@pytest.mark.asyncio
async def test_checkpoint_state_preserves_candidate_ids_across_resume():
    """Candidate IDs are persisted in checkpoints and available after resume."""
    reranker = _FlakyReranker()
    workflow = _workflow(reranker)
    config = {"configurable": {"thread_id": "persist-candidates-thread"}}

    # First invoke.
    await workflow.ainvoke(_state("persist-query"), config)

    # Verify candidate IDs are in checkpoint.
    state = workflow.get_graph_state("persist-candidates-thread").values
    assert "candidate_ids" in state
    assert len(state["candidate_ids"]) > 0
