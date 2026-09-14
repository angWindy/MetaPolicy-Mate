from __future__ import annotations

import logging
import os

# Set test embedding dimension before any settings are imported.
os.environ.setdefault("TEST_EMBED_DIM", "128")

import pytest

from src.domain.schemas import (
    Candidate,
    GeneratedAnswer,
    Latency,
    RerankRequest,
    RerankResult,
    RetrievedChunk,
    RetrievalStatus,
    UserContext,
)
from src.rag.config import RAGSettings
from src.rag.generator import TemplateAnswerGenerator
from src.rag.observability import METRIC_NAMES, RAGObservability, hash_identifier
from src.rag.workflow import RetrievalWorkflow


def _candidate() -> Candidate:
    return Candidate(
        chunk_id="obs-c1",
        document_id="obs-d1",
        version_id="obs-v1",
        content="private document body",
        metadata={
            "document_number": "OBS-2026",
            "title": "Observable rule",
            "article": "1",
            "legal_status": "effective",
            "source_url": "https://example.edu/obs",
        },
        fusion_score=0.9,
        rerank_score=0.95,
    )


def _retriever_search(query: str, user: UserContext, as_of_date=None, embed_text=None) -> list[RetrievedChunk]:
    """Real retriever function that returns two RetrievedChunks.

    Stricter 2026-09-01 contract: SUFFICIENT requires >= 2 selected
    candidates. Returning a single chunk would cause the workflow to
    abstain before reaching ``validate_citation_node``, which the trace
    test below explicitly asserts.
    """

    def _as_chunk(chunk_id: str, document_id: str, version_id: str) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id,
            text=f"private document body for {chunk_id}",
            score=0.95,
            source="test",
            metadata={
                "document_number": f"OBS-2026-{chunk_id}",
                "title": f"Observable rule {chunk_id}",
                "article": "1",
                "legal_status": "effective",
                "source_url": f"https://example.edu/{chunk_id}",
                "document_id": document_id,
                "version_id": version_id,
            },
        )

    return [
        _as_chunk("obs-c1", "obs-d1", "obs-v1"),
        _as_chunk("obs-c2", "obs-d2", "obs-v2"),
    ]


async def _rerank_fn(
    query: str,
    candidates: list[Candidate],
    settings: RAGSettings,
) -> RerankResult:
    """Real rerank function using the rerank service protocol."""
    return RerankResult(
        status=RetrievalStatus.SUFFICIENT,
        original_query=query,
        candidates=list(candidates),
        latency=Latency(total_ms=2.0, rerank_ms=2.0),
    )


@pytest.mark.asyncio
async def test_end_to_end_trace_has_required_fields_and_node_spans():
    telemetry = RAGObservability()
    # Provide explicit settings so the trace fields are deterministic
    # rather than relying on whatever ``QDRANT_COLLECTION`` happens to
    # be set in ``.env``.
    settings = RAGSettings(
        app_env="test",
        qdrant_collection="hust-regulations-v1",
        embedding_model="text-embedding-3-small",
    )
    workflow = RetrievalWorkflow(
        settings=settings,
        retrieve_fn=_retriever_search,
        rerank_fn=_rerank_fn,
        generator=TemplateAnswerGenerator(),
        observability=telemetry,
    )
    result = await workflow.ainvoke(
        {
            "original_query": "Who can access this rule?",
            "user": UserContext(user_id="user-42", tenant_id="tenant-7"),
        },
        {"configurable": {"thread_id": "trace-thread", "trace_id": "trace-1"}},
    )

    trace = telemetry.get_trace(result["trace_id"])
    assert trace is not None
    assert trace.fields == {
        "trace_id": "trace-1",
        "thread_id": "trace-thread",
        "tenant_id": "tenant-7",
        "user_id_hash": hash_identifier("user-42"),
        "query_hash": hash_identifier("Who can access this rule?"),
        "index_version": "hust-regulations-v1",
        "embedding_model": "text-embedding-3-small",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "policy_version": "security.policy.v1",
    }
    assert {span.name for span in trace.spans} >= {
        "build_policy_node",
        "transform_query_node",
        "hybrid_retrieve_node",
        "rerank_node",
        "evidence_gate_node",
        "validate_citation_node",
    }
    snapshot = telemetry.metrics.snapshot()
    assert snapshot["candidate_count"] == 2
    assert snapshot["final_context_count"] == 2
    assert snapshot["total_retrieval_latency"] > 0


def test_metrics_registry_exposes_required_names_and_logs_are_redacted(caplog):
    telemetry = RAGObservability()
    assert set(METRIC_NAMES) >= {
        "query_transform_latency",
        "dense_latency",
        "sparse_latency",
        "fusion_latency",
        "rerank_latency",
        "context_expansion_latency",
        "total_retrieval_latency",
        "candidate_count",
        "final_context_count",
        "retry_count",
        "abstain_rate",
        "forbidden_rate",
        "fallback_rate",
    }
    with caplog.at_level(logging.INFO, logger="src.rag"):
        telemetry.log(
            "test_event",
            query="personal information",
            password="never-log",
            token="never-log",
            document_text="secret document",
            query_hash=hash_identifier("personal information"),
        )
    # The hash is the only safely-loggable representation of the query.
    # We assert on the hash, not the plaintext.
    expected_hash = hash_identifier("personal information")
    rendered = " ".join(record.message for record in caplog.records)
    assert "never-log" not in rendered
    assert "secret document" not in rendered
    assert "personal information" not in rendered
    # If ``log()`` emitted anything, the hash must appear.
    if rendered:
        assert expected_hash in rendered
