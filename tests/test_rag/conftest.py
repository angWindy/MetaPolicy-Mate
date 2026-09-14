"""Pytest fixtures for the RAG test suite.

Auto-registers the shared real-service fixtures from
``tests/fixtures.py`` so every test in this directory can use them.
Also auto-marks every test in ``tests/test_rag/`` as
``requires_rag_runtime`` so CI can opt-in with ``-m requires_rag_runtime``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

# Re-export the shared fixtures so pytest picks them up for tests in this
# directory. We import here (instead of putting them in conftest.py
# directly) so other test packages can share the same definitions.
from tests.fixtures import (  # noqa: F401
    audit_recorder,
    openai_embeddings,
    cross_encoder_reranker,
    event_loop_policy,
    in_memory_store,
    postgres_session,
    qdrant_in_memory_store,
    qdrant_test_store,
    rag_settings,
    reranker_service,
    sparse_embeddings,
)


pytestmark = pytest.mark.requires_rag_runtime


@pytest.fixture
def citation_test_payload() -> Any:
    """Valid QdrantPayload with complete metadata for citation building.

    All grounding fields (document_number, section, page, source_url) are
    populated so ``_citation_has_complete_metadata`` returns True.
    """
    from src.domain.schemas import QdrantPayload

    return QdrantPayload(
        tenant_id="hust",
        document_id="93ff79c2-9d4a-4fa2-acf7-b6d3c2a4feaa",
        version_id="a9662952-e4fd-414f-9e47-d223fe57d7a4",
        chunk_id="5b46421d-4394-4b2a-a3b1-d49f43455591",
        parent_chunk_id=None,
        previous_chunk_id=None,
        next_chunk_id="6dc4878c-3d68-4624-a0a2-e3d0b464e999",
        owner_unit="TCCB",
        allowed_roles=["staff", "manager"],
        allowed_units=["TCCB"],
        classification="internal",
        status="published",
        valid_from=datetime(2026, 1, 1),
        valid_to=None,
        page=5,
        section="Điều 5",
        title="Quy chế đào tạo tín chỉ",
        document_number="10232/QĐ-ĐHBK",
        source_url="https://example.com/docs/10232",
        content_hash="sha256:deadbeef",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        sparse_model="hashed-lexical",
        sparse_version="1",
        index_version="regulations-2026-08-04",
    )


@pytest.fixture
def incomplete_citation_payload() -> Any:
    """QdrantPayload missing section and page — triggers incomplete metadata path.

    Used to test the citation validator's soft-warning path when
    ``_citation_has_complete_metadata`` returns False.
    """
    from src.domain.schemas import QdrantPayload

    return QdrantPayload(
        tenant_id="hust",
        document_id="doc-incomplete",
        version_id="version-incomplete",
        chunk_id="chunk-incomplete",
        parent_chunk_id=None,
        previous_chunk_id=None,
        next_chunk_id=None,
        owner_unit="TCCB",
        allowed_roles=["staff"],
        allowed_units=["TCCB"],
        classification="internal",
        status="published",
        valid_from=datetime(2026, 1, 1),
        valid_to=None,
        page=None,  # Missing
        section=None,  # Missing
        title="Quy chế không rõ",
        document_number="99/QĐ-ĐHBK",
        source_url=None,  # Missing
        content_hash="sha256:incomplete",
        embedding_model="text-embedding-3-small",
        embedding_version="1",
        sparse_model="hashed-lexical",
        sparse_version="1",
        index_version="regulations-2026-08-04",
    )


@pytest.fixture
def multi_tenant_payloads() -> dict[str, Any]:
    """Collection of payloads for different tenants (HUST vs HUCE).

    Used for tenant isolation tests where cross-tenant access must be denied.
    """
    from src.domain.schemas import QdrantPayload

    return {
        "hust": QdrantPayload(
            tenant_id="hust",
            document_id="doc-hust",
            version_id="version-hust",
            chunk_id="chunk-hust",
            parent_chunk_id=None,
            previous_chunk_id=None,
            next_chunk_id=None,
            owner_unit="TCCB",
            allowed_roles=["staff"],
            allowed_units=["TCCB"],
            classification="internal",
            status="published",
            valid_from=datetime(2026, 1, 1),
            valid_to=None,
            page=3,
            section="Điều 3",
            title="Quy định nghỉ phép HUST",
            document_number="01/QĐ-HUST",
            source_url="https://hust.edu.vn/rules/01",
            content_hash="sha256:hust123",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            sparse_model="hashed-lexical",
            sparse_version="1",
            index_version="regulations-2026-08-04",
        ),
        "huce": QdrantPayload(
            tenant_id="huce",
            document_id="doc-huce",
            version_id="version-huce",
            chunk_id="chunk-huce",
            parent_chunk_id=None,
            previous_chunk_id=None,
            next_chunk_id=None,
            owner_unit="HC",
            allowed_roles=["staff"],
            allowed_units=["HC"],
            classification="internal",
            status="published",
            valid_from=datetime(2026, 1, 1),
            valid_to=None,
            page=1,
            section="Điều 1",
            title="Quy định nghỉ phép HUCE",
            document_number="01/QĐ-HUCE",
            source_url="https://huce.edu.vn/rules/01",
            content_hash="sha256:huce456",
            embedding_model="text-embedding-3-small",
            embedding_version="1",
            sparse_model="hashed-lexical",
            sparse_version="1",
            index_version="regulations-2026-08-04",
        ),
    }


@pytest.fixture(autouse=True)
def _reset_retrieval_cache():
    """Clear the in-memory retrieval cache between tests.

    The cache is a module-level singleton so it persists across tests.
    Without this fixture, a test that runs after another test with the
    same (query, tenant, top_k) would receive a cached result and
    silently bypass the actual retriever/reranker — masking real
    regressions. Reset on every test to keep the test graph honest.
    """
    try:
        from src.retrieval.retrieval_cache import get_retrieval_cache

        get_retrieval_cache().clear()
    except ImportError:
        pass
    yield
    try:
        from src.retrieval.retrieval_cache import get_retrieval_cache

        get_retrieval_cache().clear()
    except ImportError:
        pass


def pytest_collection_modifyitems(config, items):
    """Mark every collected test in this package with ``requires_rag_runtime``."""
    marker = pytest.mark.requires_rag_runtime
    for item in items:
        if "tests/test_rag/" in str(item.fspath):
            item.add_marker(marker)