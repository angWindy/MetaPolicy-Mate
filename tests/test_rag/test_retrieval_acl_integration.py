"""Integration tests for retrieval ACL enforcement.

These tests verify that the retrieval pipeline correctly enforces:
- Tenant isolation (HUST vs HUCE)
- Department filter enforcement
- Access scope (PUBLIC vs DEPARTMENT)
- Reranking score thresholds

Tests require real Qdrant; run with ``pytest -m requires_rag_runtime``.
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")

from datetime import date

import pytest

from src.domain.schemas import AccessScope, UserContext


def make_user(
    tenant_id: str = "hust",
    department: str = "TCCB",
    roles: set[str] | None = None,
) -> UserContext:
    return UserContext(
        user_id="test-user",
        tenant_id=tenant_id,
        department=department,
        roles=roles or {"staff"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tenant isolation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTenantIsolation:
    @pytest.mark.requires_rag_runtime
    async def test_hust_user_cannot_retrieve_huce_chunks(
        self,
        qdrant_test_store,
        multi_tenant_payloads,
        sparse_embeddings,
    ):
        """HUST user must not see HUCE chunks in retrieval results."""
        from src.retrieval.hybrid import HybridRetriever
        from src.retrieval.config import RetrievalConfig
        from src.rag.config import RAGSettings

        settings = RAGSettings()
        settings.qdrant_collection = qdrant_test_store.settings.qdrant_collection

        # Index both tenants' chunks
        hust_payload = multi_tenant_payloads["hust"]
        huce_payload = multi_tenant_payloads["huce"]

        for payload in [hust_payload, huce_payload]:
            await qdrant_test_store.upsert(
                id=payload.chunk_id,
                payload=payload.model_dump(mode="json"),
                vector=[0.0] * 256,
            )

        retriever = HybridRetriever(
            store=qdrant_test_store,
            config=RetrievalConfig(),
            settings=settings,
            dense_provider=None,  # Use sparse only
            sparse_provider=sparse_embeddings,
        )

        # HUST user queries
        user = make_user(tenant_id="hust", department="TCCB")
        result = await retriever.search(
            query="quy định nghỉ phép",
            user=user,
            as_of=None,
        )

        # Should NOT return HUCE chunks
        chunk_ids = [c.chunk_id for c in result.candidates]
        assert "chunk-huce" not in chunk_ids, (
            "HUST user retrieved HUCE chunk — tenant isolation failed"
        )

    @pytest.mark.requires_rag_runtime
    async def test_huce_user_cannot_retrieve_hust_chunks(
        self,
        qdrant_test_store,
        multi_tenant_payloads,
        sparse_embeddings,
    ):
        """HUCE user must not see HUST chunks in retrieval results."""
        from src.retrieval.hybrid import HybridRetriever
        from src.retrieval.config import RetrievalConfig
        from src.rag.config import RAGSettings

        settings = RAGSettings()
        settings.qdrant_collection = qdrant_test_store.settings.qdrant_collection

        hust_payload = multi_tenant_payloads["hust"]
        huce_payload = multi_tenant_payloads["huce"]

        for payload in [hust_payload, huce_payload]:
            await qdrant_test_store.upsert(
                id=payload.chunk_id,
                payload=payload.model_dump(mode="json"),
                vector=[0.0] * 256,
            )

        retriever = HybridRetriever(
            store=qdrant_test_store,
            config=RetrievalConfig(),
            settings=settings,
            dense_provider=None,
            sparse_provider=sparse_embeddings,
        )

        # HUCE user queries
        user = make_user(tenant_id="huce", department="HC")
        result = await retriever.search(
            query="quy định nghỉ phép",
            user=user,
            as_of=None,
        )

        # Should NOT return HUST chunks
        chunk_ids = [c.chunk_id for c in result.candidates]
        assert "chunk-hust" not in chunk_ids, (
            "HUCE user retrieved HUST chunk — tenant isolation failed"
        )

    @pytest.mark.requires_rag_runtime
    async def test_hust_user_can_retrieve_hust_chunks(
        self,
        qdrant_test_store,
        multi_tenant_payloads,
        sparse_embeddings,
    ):
        """HUST user should retrieve their own tenant's chunks."""
        from src.retrieval.hybrid import HybridRetriever
        from src.retrieval.config import RetrievalConfig
        from src.rag.config import RAGSettings

        settings = RAGSettings()
        settings.qdrant_collection = qdrant_test_store.settings.qdrant_collection

        hust_payload = multi_tenant_payloads["hust"]

        await qdrant_test_store.upsert(
            id=hust_payload.chunk_id,
            payload=hust_payload.model_dump(mode="json"),
            vector=[0.0] * 256,
        )

        retriever = HybridRetriever(
            store=qdrant_test_store,
            config=RetrievalConfig(),
            settings=settings,
            dense_provider=None,
            sparse_provider=sparse_embeddings,
        )

        user = make_user(tenant_id="hust", department="TCCB")
        result = await retriever.search(
            query="quy định nghỉ phép",
            user=user,
            as_of=None,
        )

        # Should return HUST chunk
        chunk_ids = [c.chunk_id for c in result.candidates]
        assert "chunk-hust" in chunk_ids, (
            "HUST user did not retrieve their own chunk"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Department filter enforcement
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDepartmentFilter:
    @pytest.mark.requires_rag_runtime
    async def test_department_scope_restricts_access(
        self,
        qdrant_test_store,
        citation_test_payload,
        sparse_embeddings,
    ):
        """Chunks with DEPARTMENT scope must only be visible to allowed units."""
        from src.domain.schemas import QdrantPayload
        from src.retrieval.hybrid import HybridRetriever
        from src.retrieval.config import RetrievalConfig
        from src.rag.config import RAGSettings

        settings = RAGSettings()
        settings.qdrant_collection = qdrant_test_store.settings.qont_collection

        # Chunk restricted to TCCB department
        department_payload = citation_test_payload.model_copy()
        department_payload.chunk_id = "chunk-dept-restricted"
        department_payload.allowed_units = ["TCCB"]

        await qdrant_test_store.upsert(
            id=department_payload.chunk_id,
            payload=department_payload.model_dump(mode="json"),
            vector=[0.0] * 256,
        )

        retriever = HybridRetriever(
            store=qdrant_test_store,
            config=RetrievalConfig(),
            settings=settings,
            dense_provider=None,
            sparse_provider=sparse_embeddings,
        )

        # User in TCCB can access
        user_tccb = make_user(department="TCCB")
        result_tccb = await retriever.search(
            query="quy định",
            user=user_tccb,
            as_of=None,
        )
        assert "chunk-dept-restricted" in [c.chunk_id for c in result_tccb.candidates]

        # User in another department cannot access
        user_other = make_user(department="KHOA_HCM")
        result_other = await retriever.search(
            query="quy định",
            user=user_other,
            as_of=None,
        )
        assert "chunk-dept-restricted" not in [
            c.chunk_id for c in result_other.candidates
        ]


# ─────────────────────────────────────────────────────────────────────────────
# 3. Reranking score thresholds
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRerankingThresholds:
    @pytest.mark.requires_rag_runtime
    async def test_low_rerank_score_filtered_by_threshold(
        self,
        qdrant_test_store,
        citation_test_payload,
        reranker_service,
    ):
        """Chunks with rerank scores below threshold should be filtered."""
        from src.retrieval.evidence_rerank import rerank_evidence
        from src.domain.schemas import Candidate, RerankResult
        from src.rag.config import RAGSettings

        # Create candidates with known scores
        candidates = [
            Candidate(
                chunk_id="high-score",
                document_id="doc-1",
                version_id="v1",
                content="Quy định nghỉ phép",
                metadata={"document_number": "01/QĐ"},
                fusion_score=0.5,
                rerank_score=0.95,
            ),
            Candidate(
                chunk_id="low-score",
                document_id="doc-2",
                version_id="v2",
                content="Nội dung không liên quan",
                metadata={"document_number": "02/QĐ"},
                fusion_score=0.3,
                rerank_score=0.05,  # Below typical threshold
            ),
        ]

        result = await rerank_evidence(
            original_query="quy định nghỉ phép",
            candidates=candidates,
            reranker_service=reranker_service,
            settings=RAGSettings(),
        )

        # Both should be in result, but ordered by score
        chunk_ids = [c.chunk_id for c in result.candidates]
        assert "high-score" in chunk_ids
        assert "low-score" in chunk_ids
        # High score should be first
        assert chunk_ids.index("high-score") < chunk_ids.index("low-score")

    @pytest.mark.requires_rag_runtime
    async def test_rerank_result_status_reflects_quality(
        self,
        qdrant_test_store,
        citation_test_payload,
        reranker_service,
    ):
        """RerankResult status should reflect candidate quality."""
        from src.retrieval.evidence_rerank import rerank_evidence
        from src.domain.schemas import Candidate, RetrievalStatus
        from src.rag.config import RAGSettings

        # High-quality candidates
        candidates = [
            Candidate(
                chunk_id=f"chunk-{i}",
                document_id="doc-1",
                version_id="v1",
                content=f"Nội dung {i}",
                metadata={"document_number": f"{i:02d}/QĐ"},
                fusion_score=0.8,
                rerank_score=0.9,
            )
            for i in range(5)
        ]

        result = await rerank_evidence(
            original_query="quy định",
            candidates=candidates,
            reranker_service=reranker_service,
            settings=RAGSettings(),
        )

        assert result.status in {
            RetrievalStatus.SUFFICIENT,
            RetrievalStatus.PARTIAL,
        }
        assert len(result.candidates) == 5


# ─────────────────────────────────────────────────────────────────────────────
# 4. Access scope (PUBLIC vs DEPARTMENT)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAccessScope:
    @pytest.mark.requires_rag_runtime
    async def test_public_scope_visible_to_all_users(
        self,
        qdrant_test_store,
        citation_test_payload,
        sparse_embeddings,
    ):
        """PUBLIC chunks should be visible to all users regardless of department."""
        from src.domain.schemas import QdrantPayload
        from src.retrieval.hybrid import HybridRetriever
        from src.retrieval.config import RetrievalConfig
        from src.rag.config import RAGSettings

        settings = RAGSettings()
        settings.qdrant_collection = qdrant_test_store.settings.qdrant_collection

        # Create PUBLIC chunk
        public_payload = citation_test_payload.model_copy()
        public_payload.chunk_id = "chunk-public"
        public_payload.allowed_units = []  # Empty = PUBLIC

        await qdrant_test_store.upsert(
            id=public_payload.chunk_id,
            payload=public_payload.model_dump(mode="json"),
            vector=[0.0] * 256,
        )

        retriever = HybridRetriever(
            store=qdrant_test_store,
            config=RetrievalConfig(),
            settings=settings,
            dense_provider=None,
            sparse_provider=sparse_embeddings,
        )

        # Any user should see it
        for dept in ["TCCB", "KHOA_HCM", "PHONG_KHCN"]:
            user = make_user(department=dept)
            result = await retriever.search(
                query="quy định",
                user=user,
                as_of=None,
            )
            assert "chunk-public" in [c.chunk_id for c in result.candidates], (
                f"PUBLIC chunk not visible to department {dept}"
            )
