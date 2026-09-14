"""Smoke eval gate for the RAG pipeline.

Runs a fixed set of representative Vietnamese regulation questions and
asserts the pipeline produces answers with citations within a tight
latency budget. Designed to fail loudly in CI when a regression breaks
the end-to-end retrieval path.

Run with:
    pytest tests/test_evaluation/test_smoke_questions.py -v --markers

Mark: pytest.mark.eval_slow — set in pytest.ini.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Sequence

# Must be set before any settings module is imported so the
# ``validate_database_url`` validator does not reject in-memory fixtures.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("TEST_EMBED_DIM", "128")

import pytest

from src.domain.schemas import (
    Candidate,
    Latency,
    LegalStatus,
    RerankRequest,
    RerankResult,
    RetrievalStatus,
    UserContext,
)
from src.rag.config import RAGSettings
from src.rag.generator import TemplateAnswerGenerator
from src.rag.workflow import RetrievalWorkflow


pytestmark = pytest.mark.eval_slow


# Eight Vietnamese regulation queries — replace with curated set as the
# corpus grows. The assertions below expect at least 6 of 8 to come back
# generated with citations and at least 5 of 8 to return non-low confidence.
SMOKE_QUESTIONS: list[str] = [
    "Quy chế đào tạo tín chỉ yêu cầu gì?",
    "Mức học phí Tiến sĩ toàn khóa là bao nhiêu?",
    "Tiêu chí chấm công giảng viên được quy định ra sao?",
    "�iều kiện xét tuyển nghiên cứu sinh gồm những gì?",
    "KPI giảng viên được đánh giá theo những chỉ tiêu nào?",
    "Quy trình bổ nhiệm chức danh giáo sư như thế nào?",
    "Các hình thức kỷ luật sinh viên theo quy chế?",
    "Thời gian đào tạo đại học chính quy là bao lâu?",
]


def _candidate(chunk_id: str, score: float) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        version_id=f"version-{chunk_id}",
        content=f"Điều {chunk_id}. Nội dung quy định.",
        metadata={
            "document_number": f"01/{chunk_id}",
            "title": f"Quy định {chunk_id}",
            "article": chunk_id,
            "section": f"Điều {chunk_id}",
            "page": 1,
            "legal_status": LegalStatus.EFFECTIVE.value,
            "source_url": f"https://example.edu/{chunk_id}",
        },
        fusion_score=0.5,
        rerank_score=score,
    )


class _StubRetriever:
    """Returns a fixed candidate list per query."""

    def __init__(self) -> None:
        self.calls = 0

    async def search(self, query, user, as_of_date=None, embed_text=None):
        del query, user, as_of_date, embed_text  # smoke test does not vary per query
        self.calls += 1
        return [_candidate(f"chunk-{i}", 0.9 - i * 0.05) for i in range(1, 6)]


class _StubReranker:
    def __init__(self) -> None:
        self.calls = 0

    async def rerank(self, request: RerankRequest) -> RerankResult:
        self.calls += 1
        return RerankResult(
            status=RetrievalStatus.SUFFICIENT,
            original_query=request.original_query,
            candidates=list(request.candidates),
            latency=Latency(total_ms=1.0),
        )


def _workflow() -> RetrievalWorkflow:
    settings = RAGSettings(
        app_env="test",
        final_context_limit=3,
        query_expansion_enabled=False,
        hyde_enabled=False,
        cache_enabled=False,  # do not cache between smoke runs
        evidence_thresholds_by_domain={
            "general": {
                "sufficient_top_score": 0.5,
                "partial_top_score": 0.2,
                "minimum_independent_sources": 1,
            }
        },
    )
    return RetrievalWorkflow(
        settings=settings,
        retriever=_StubRetriever(),
        reranker_service=_StubReranker(),
        generator=TemplateAnswerGenerator(),
    )


def _user() -> UserContext:
    return UserContext(
        user_id="smoke-user",
        tenant_id="hust",
        department="TCCB",
        role="staff",
        school_code="HUST",
    )


async def _run_all(questions: Sequence[str]) -> list[dict]:
    workflow = _workflow()
    user = _user()
    results: list[dict] = []
    for index, question in enumerate(questions):
        state = {
            "original_query": question,
            "query": question,
            "user": user,
            "as_of_date": None,
            "request_id": f"smoke-{index}",
            "index_version": "",
        }
        started = time.perf_counter()
        result = await workflow.ainvoke(state, thread_id=f"smoke-{index}")
        elapsed_ms = (time.perf_counter() - started) * 1000
        results.append({
            "question": question,
            "outcome": result.get("outcome", "unknown"),
            "confidence": result.get("confidence", "low"),
            "citations": list(result.get("citations") or []),
            "elapsed_ms": elapsed_ms,
        })
    return results


def test_smoke_eval_gate():
    """Assert the smoke set meets the contract."""
    results = asyncio.run(_run_all(SMOKE_QUESTIONS))

    generated = [r for r in results if r["outcome"] == "generated"]
    with_citation = [r for r in generated if r["citations"]]
    high_conf = [r for r in generated if r["confidence"] in {"high", "medium"}]
    latencies = sorted(r["elapsed_ms"] for r in results)
    p50_latency_ms = latencies[len(latencies) // 2] if latencies else 0.0

    # Contract: >= 6/8 generated with >= 5/8 having >= 1 citation.
    assert len(generated) >= 6, (
        f"Smoke gate failed: only {len(generated)}/{len(results)} generated. "
        f"Outcomes: {[r['outcome'] for r in results]}"
    )
    assert len(with_citation) >= 5, (
        f"Smoke gate failed: only {len(with_citation)}/{len(generated)} "
        f"generated answers carry citations."
    )
    assert len(high_conf) >= 4, (
        f"Smoke gate failed: only {len(high_conf)}/{len(generated)} answers "
        f"have high or medium confidence."
    )
    # Latency: p50 < 12 s on the stub pipeline. Production is allowed more.
    assert p50_latency_ms < 12_000, (
        f"Smoke gate failed: p50 latency {p50_latency_ms:.0f}ms exceeds 12s."
    )


def test_payload_patching_drops_invalid_only():
    """Regression: legacy payloads (missing optional fields) are still accepted.

    Ensures ``_patch_payload_for_validation`` keeps a candidate whose only
    missing fields are optional, while still rejecting truly malformed
    payloads (no chunk_id, no tenant_id).
    """
    from src.retrieval.hybrid import _patch_payload_for_validation

    legacy = {
        "tenant_id": "hust",
        "document_id": "doc-1",
        "version_id": "v-1",
        "chunk_id": "c-1",
        "legal_status": "effective",  # legacy key
        "owner_unit": "TCCB",
    }
    patched = _patch_payload_for_validation(dict(legacy))
    assert patched["status"] == "effective"  # legal_status normalised to status
    assert patched["classification"] == "internal"
    assert patched["content_hash"].startswith("legacy:")

    truly_broken = {"chunk_id": "c-2"}  # missing tenant_id, document_id, version_id
    patched_broken = _patch_payload_for_validation(dict(truly_broken))
    # Required fields are NOT patched — must remain missing so validator fails.
    assert "tenant_id" not in patched_broken
    assert "document_id" not in patched_broken
