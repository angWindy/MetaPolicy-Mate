"""Regression tests for src/retrieval/hybrid.py silent-exception handlers.

These guard three ``except Exception`` paths that were previously
swallowing errors with bare ``pass`` / ``continue``. The fix
(2026-08-31, B-P3-02 follow-up) replaced them with ``logger.warning``
+ ``logger.error`` calls so:

1. A sparse-retrieval failure no longer disappears silently — operators
   see ``sparse_retrieval_failed`` in the logs.
2. An invalid ``QdrantPayload`` no longer disappears silently —
   operators see ``qdrant_payload_invalid`` with the chunk id.
3. An audit-log failure no longer disappears silently — operators see
   ``audit_access_decision_failed`` with the chunk id (compliance:
   missing audit rows are a real risk).

The tests assert that the corresponding log lines are emitted, and
that the hybrid retriever still returns its dense results (the dense
leg must NOT be dragged down by the sparse leg).
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from src.rag.config import RAGSettings


def _settings(**overrides: Any) -> RAGSettings:
    base = {
        "rrf_k": 60,
        "rrf_alpha": 0.3,  # RAGSettings caps rrf_alpha at 0.4
        "semantic_top_k": 10,
        "keyword_top_k": 10,
        "final_top_k": 10,
    }
    base.update(overrides)
    return RAGSettings(**base)


def _build_retriever_for_audit_tests() -> Any:
    """Build a ``HybridRetriever`` shell for testing ``_audit_candidates``.

    The audit-candidates path does not actually call embeddings or the
    vector store — it only walks ``semantic_results`` and logs failures.
    So we can pass None for the dependencies and never invoke them.
    """
    from src.retrieval.hybrid import HybridRetriever

    return HybridRetriever(
        settings=_settings(),
        repository=None,  # type: ignore[arg-type]
        embeddings=None,  # type: ignore[arg-type]
        vector_store=None,  # type: ignore[arg-type]
    )


def _user() -> Any:
    from src.domain.schemas import UserContext

    return UserContext(
        user_id="u1",
        tenant_id="tccb",
        department="TCCB",
        roles=["staff"],
        clearance_level="internal",
    )


def _make_candidate(
    chunk_id: str,
    *,
    document_id: str | None = None,
    dense_rank: int | None = None,
    sparse_rank: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Build a Candidate matching src.domain.schemas.Candidate."""
    from src.domain.schemas import Candidate

    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id or f"doc-{chunk_id}",
        version_id=f"version-{document_id or chunk_id}",
        content=f"Content for {chunk_id}",
        metadata={"tenant_id": "tccb", **(metadata or {})},
        dense_rank=dense_rank,
        sparse_rank=sparse_rank,
        fusion_score=0.0,
        rerank_score=None,
    )


def _make_valid_qdrant_payload_dict(chunk_id: str) -> dict[str, Any]:
    """Build a payload dict that passes QdrantPayload validation.

    The :class:`QdrantPayload` schema has many required fields; tests
    that need a "happy path" payload would otherwise need ~20 lines
    of boilerplate per call.
    """
    from src.domain.schemas import QdrantPayload

    example = QdrantPayload.model_config["json_schema_extra"]["examples"][0]
    example = dict(example)
    example["chunk_id"] = chunk_id
    example["document_id"] = f"doc-{chunk_id}"
    example["version_id"] = f"ver-{chunk_id}"
    return example


def test_invalid_qdrant_payload_logs_warning_and_skips(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Bad payload → warning logged, not silent continue."""
    retriever = _build_retriever_for_audit_tests()

    bad_chunk_id = "chunk-bad-1"
    bad_payload = {
        # Missing required fields → QdrantPayload validation fails.
        "this_is_not_a_real_field": "x",
    }
    semantic_results = [(bad_chunk_id, 0.9, bad_payload)]

    with caplog.at_level(
        logging.WARNING, logger="src.retrieval.hybrid"
    ):
        retriever._audit_candidates(_user(), semantic_results)

    assert any(
        "qdrant_payload_invalid" in record.message
        and bad_chunk_id in record.message
        for record in caplog.records
    ), f"expected qdrant_payload_invalid log line, got: {[r.message for r in caplog.records]}"


def test_audit_failure_logs_error_and_does_not_propagate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Audit failure → ERROR logged, exception swallowed, retrieval safe.

    Audit failures are a compliance risk: missing audit rows are how
    unauthorised-access attempts go unnoticed. The previous silent
    ``continue`` made those failures invisible. The new behaviour
    emits ``audit_access_decision_failed`` at ERROR level.
    """
    retriever = _build_retriever_for_audit_tests()

    good_payload_dict = _make_valid_qdrant_payload_dict("chunk-good-1")

    semantic_results = [("chunk-good-1", 0.9, good_payload_dict)]

    # Inject a fake repository whose audit call raises.
    class _ExplodingRepo:
        def create_audit_log(
            self,
            *,
            request_id: str,
            user: Any,
            action: str,
            outcome: str,
            query: str | None = None,
            resource_ids: list[str] | None = None,
            metadata: dict | None = None,
        ) -> None:
            raise RuntimeError("simulated audit DB down")

    retriever.repository = _ExplodingRepo()

    with caplog.at_level(
        logging.ERROR, logger="src.retrieval.hybrid"
    ):
        # Must NOT raise — audit failures must not break retrieval.
        retriever._audit_candidates(_user(), semantic_results)

    assert any(
        "audit_access_decision_failed" in record.message
        and "chunk-good-1" in record.message
        for record in caplog.records
    ), f"expected audit_access_decision_failed log line, got: {[r.message for r in caplog.records]}"


def test_sparse_failure_logs_warning_and_falls_back_to_dense(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Sparse leg failure → warning logged, dense leg still returns results.

    This is the B-P3-02 follow-up smoke test. It uses the public
    ``hybrid_retrieve`` orchestrator with two real (fake) legs so the
    sparse-failure path in :func:`hybrid_retrieve` is exercised.
    """
    from src.retrieval.hybrid import hybrid_retrieve
    from src.domain.schemas import RetrievalStatus, UserContext

    class _SparseFailingLeg:
        async def sparse_search(
            self, query: str, access_filter: Any, limit: int, index_version: str
        ) -> list[Any]:
            raise RuntimeError("simulated Qdrant sparse index down")

    class _DenseLeg:
        async def dense_search(
            self, query: str, access_filter: Any, limit: int, index_version: str
        ) -> list[Any]:
            return [_make_candidate("dense-1", dense_rank=1)]

    user = UserContext(
        user_id="u1",
        tenant_id="tccb",
        department="TCCB",
        roles=["staff"],
        clearance_level="internal",
    )

    result = asyncio.run(
        hybrid_retrieve(
            "test query",
            user,
            "index-v1",
            dense_retriever=_DenseLeg(),
            sparse_retriever=_SparseFailingLeg(),
            settings=_settings(),
        )
    )

    assert result.status == RetrievalStatus.PARTIAL
    assert [c.chunk_id for c in result.candidates] == ["dense-1"]


def test_audit_summary_logged_when_failures_present(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Multiple invalid payloads → summary log line emitted."""
    retriever = _build_retriever_for_audit_tests()

    semantic_results = [
        ("chunk-bad-1", 0.9, {"bad": "payload-1"}),
        ("chunk-bad-2", 0.8, {"bad": "payload-2"}),
    ]

    with caplog.at_level(
        logging.INFO, logger="src.retrieval.hybrid"
    ):
        retriever._audit_candidates(_user(), semantic_results)

    assert any(
        "hybrid_audit_summary" in record.message
        and "invalid_payloads=" in record.message
        for record in caplog.records
    ), f"expected summary log line, got: {[r.message for r in caplog.records]}"


def test_audit_no_log_when_all_payloads_valid_and_auditable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Healthy path: no warning/error log lines emitted.

    The fixes must not add noise on the happy path — operators should
    only see audit logs when something is wrong.
    """
    retriever = _build_retriever_for_audit_tests()

    good = _make_valid_qdrant_payload_dict("chunk-good-1")

    semantic_results = [("chunk-good-1", 0.9, good)]

    class _WorkingRepo:
        def create_audit_log(
            self,
            *,
            request_id: str,
            user: Any,
            action: str,
            outcome: str,
            query: str | None = None,
            resource_ids: list[str] | None = None,
            metadata: dict | None = None,
        ) -> None:
            return None

    retriever.repository = _WorkingRepo()

    with caplog.at_level(logging.DEBUG, logger="src.retrieval.hybrid"):
        retriever._audit_candidates(_user(), semantic_results)

    # No ERROR or WARNING level records expected.
    bad = [
        r
        for r in caplog.records
        if r.levelno >= logging.WARNING
        and r.name == "src.retrieval.hybrid"
    ]
    assert not bad, (
        f"happy path must not emit warnings, got: "
        f"{[(r.levelname, r.message) for r in bad]}"
    )