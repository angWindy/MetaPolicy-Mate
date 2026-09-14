"""End-to-end routing tests for the new retrieval workflow graph.

The 2026-09-01 redesign adds two short-circuit branches at the head
of the graph: ``chitchat_response_node`` (SMALL_TALK) and
``decompose_query_node`` (MULTI_INTENT). These tests pin down the
routing so any future refactor cannot silently bypass retrieval cost
or skip decomposition.
"""

from __future__ import annotations

import os

# Must be set before any settings module is imported so the
# ``validate_database_url`` validator does not reject in-memory fixtures.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("TEST_EMBED_DIM", "128")

import pytest

from src.domain.schemas import (
    Candidate,
    Latency,
    RerankRequest,
    RerankResult,
    RetrievalStatus,
    UserContext,
)
from src.rag.config import RAGSettings
from src.rag.generator import TemplateAnswerGenerator
from src.rag.intent_router import QueryIntent
from src.rag.workflow import RetrievalState, RetrievalWorkflow


def _candidate(chunk_id: str = "chunk-1", score: float = 0.95) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        version_id=f"version-{chunk_id}",
        content=f"Nội dung {chunk_id}.",
        metadata={
            "document_number": f"01/{chunk_id}",
            "title": "Quy định",
            "article": "5",
            "legal_status": "effective",
            "source_url": f"https://example.edu/{chunk_id}",
        },
        fusion_score=0.5,
        rerank_score=score,
    )


class _StubRetriever:
    """Counts how many times the retriever is invoked."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, user, as_of_date=None, embed_text=None):
        del embed_text  # HyDE token; ignored by this stub
        self.calls += 1
        return [_candidate()]


class _StubReranker:
    def __init__(self, status: RetrievalStatus = RetrievalStatus.SUFFICIENT) -> None:
        self.status = status
        self.calls = 0

    async def rerank(self, request: RerankRequest) -> RerankResult:
        self.calls += 1
        return RerankResult(
            status=self.status,
            original_query=request.original_query,
            candidates=list(request.candidates),
            latency=Latency(total_ms=1.0),
        )


def _workflow(retriever: _StubRetriever, reranker: _StubReranker) -> RetrievalWorkflow:
    return RetrievalWorkflow(
        settings=RAGSettings(
            app_env="test",
            final_context_limit=3,
            query_expansion_enabled=False,
            hyde_enabled=False,
            evidence_thresholds_by_domain={
                "general": {
                    "sufficient_top_score": 0.7,
                    "partial_top_score": 0.3,
                    "minimum_independent_sources": 1,
                }
            },
        ),
        retriever=retriever,
        reranker_service=reranker,
        generator=TemplateAnswerGenerator(),
    )


def _initial_state(query: str) -> RetrievalState:
    return {
        "original_query": query,
        "user": UserContext(user_id="u-1", tenant_id="hust", department="TCCB"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Small-talk short-circuit
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "xin chào",
        "Xin chào!",
        "cảm ơn",
        "tạm biệt",
        "bye",
        "hello",
        "hi",
    ],
)
async def test_workflow_skips_retrieval_for_small_talk(query: str):
    """SMALL_TALK must short-circuit at ``chitchat_response_node``.

    The retriever must NOT be called for small-talk. We also assert
    that the workflow visits ``chitchat_response_node`` and exits
    cleanly without entering the retrieval subgraph.
    """

    retriever = _StubRetriever()
    reranker = _StubReranker()
    workflow = _workflow(retriever, reranker)
    result = await workflow.ainvoke(_initial_state(query))

    # No retrieval cost was paid for the small-talk query.
    assert retriever.calls == 0
    assert reranker.calls == 0
    # Routing: build_user_context → classify_intent → chitchat_response.
    assert "classify_intent_node" in result["visited"]
    assert "chitchat_response_node" in result["visited"]
    # The full retrieval pipeline did NOT run.
    assert "hybrid_retrieve_node" not in result["visited"]
    assert "rerank_node" not in result["visited"]
    assert "validate_citation_node" not in result["visited"]
    assert result["outcome"] == "chitchat_response"
    # No citations because the chitchat template is hallucination-free.
    assert result["citations"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_intent", "expected_text"),
    [
        ("Bạn là ai?", QueryIntent.SELF_INTRODUCTION, "trợ lý AI P-234 PolicyMeta"),
        ("Bạn có thể làm gì?", QueryIntent.HELP, "cung cấp trích dẫn"),
        ("Xin chào, bạn có các tác dụng gì?", QueryIntent.HELP, "tìm tài liệu"),
    ],
)
async def test_workflow_answers_assistant_queries_without_retrieval(
    query: str,
    expected_intent: QueryIntent,
    expected_text: str,
):
    retriever = _StubRetriever()
    reranker = _StubReranker()
    result = await _workflow(retriever, reranker).ainvoke(_initial_state(query))

    assert result["intent"] is expected_intent
    assert retriever.calls == 0
    assert reranker.calls == 0
    assert "chitchat_response_node" in result["visited"]
    assert "hybrid_retrieve_node" not in result["visited"]
    assert result["citations"] == []
    assert result["cited_chunk_ids"] == []
    assert result["confidence"] == "high"
    assert result["outcome"] == "chitchat_response"
    assert expected_text in result["answer"]


# ─────────────────────────────────────────────────────────────────────────────
# Multi-intent decomposition
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_routes_multi_intent_to_decompose_node():
    """MULTI_INTENT must route to ``decompose_query_node`` before retrieval.

    The decompose node runs each sub-query against the retrieval subgraph
    and merges the results. The routing check is "the decompose node was
    visited and the merge produced a multi-intent trace"; the final
    ``outcome`` field reflects whatever the subgraph produces (abstain
    when the strict SUFFICIENT contract is not met by the stub
    retriever).
    """

    retriever = _StubRetriever()
    reranker = _StubReranker()
    workflow = _workflow(retriever, reranker)
    result = await workflow.ainvoke(
        _initial_state(
            "Quy chế chi tiêu nội bộ áp dụng cho HUCE không? Và HUST thì sao?"
        )
    )

    # The intent classifier must route through decompose_query_node.
    assert "classify_intent_node" in result["visited"]
    assert "decompose_query_node" in result["visited"]
    # After decompose, the subgraph still runs the rest of the
    # pipeline (the decompose node is a fan-out, not a terminal
    # node). The stub retriever only returns one chunk, so the strict
    # SUFFICIENT contract downgrades the result to ABSTAIN.
    assert result["outcome"] in {"abstained", "multi_intent_response", "unverified"}


@pytest.mark.asyncio
async def test_workflow_skips_decompose_for_simple_question():
    """A single semantic question must NOT enter the decompose node."""

    retriever = _StubRetriever()
    reranker = _StubReranker()
    workflow = _workflow(retriever, reranker)
    result = await workflow.ainvoke(
        _initial_state("Quy chế chi tiêu nội bộ điều 5 khoản 2 nói gì?")
    )

    assert "classify_intent_node" in result["visited"]
    assert "decompose_query_node" not in result["visited"]
    assert "hybrid_retrieve_node" in result["visited"]
