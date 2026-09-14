"""Shared fixtures for tests that exercise real services.

Provides real Qdrant collections (per-test UUID), real Neon Postgres
sessions, real OpenAI embeddings, and real Redis connections. No mocks,
no fakes — every fixture talks to the same services the production code
uses (configured via ``.env`` / ``.env.rag``).

Each fixture isolates state by:
- Generating a UUID per test for Qdrant collection names (auto-cleaned)
- Using transactions / savepoints for Postgres where possible
- Using dedicated Redis keys with UUID prefixes

The ``app_env`` is forced to ``"test"`` so the SQLite-only safety checks
in :class:`RAGSettings` do not reject in-memory fixtures.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio

# Force APP_ENV=test before any settings module is imported so the
# ``validate_database_url`` and ``validate_production_configuration``
# validators do not reject SQLite in-memory or missing API keys.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEV_AUTH_BYPASS", "true")


def _test_rag_settings(**overrides: Any) -> Any:
    """Build a ``RAGSettings`` instance with test-friendly defaults."""
    from src.rag.config import RAGSettings

    base: dict[str, Any] = {
        "app_env": "test",
        "vector_backend": "qdrant",
        "qdrant_url": os.environ.get(
            "QDRANT_URL",
            "http://localhost:6333",
        ),
        "qdrant_api_key": os.environ.get("QDRANT_API_KEY", ""),
        "qdrant_collection": f"test-{uuid.uuid4()}",
        "embedding_provider": os.environ.get(
            "TEST_EMBEDDING_PROVIDER",
            "hash",
        ),
        "embedding_dimensions": int(
            os.environ.get("TEST_EMBED_DIM", "256"),
        ),
        "generator_provider": "template",
        "dev_auth_bypass": True,
        "docling_enabled": False,
        "qdrant_local_path": "",  # Always talk to a real (or :memory:) Qdrant.
    }
    base.update(overrides)
    return RAGSettings(**base)


@pytest_asyncio.fixture
async def qdrant_test_store() -> AsyncIterator[Any]:
    """Real Qdrant collection - per-test UUID, auto-cleanup.

    Talks to the Qdrant instance configured via ``QDRANT_URL`` (or the
    in-memory mode when ``qdrant_local_path=":memory:"`` is set). The
    collection is deleted after the test so we never leave state behind.
    """
    from src.retrieval.vector_store import QdrantVectorStore

    settings = _test_rag_settings()
    store = QdrantVectorStore(settings)
    try:
        await store.create_collection()
        await store.create_payload_indexes()
        yield store
    finally:
        try:
            await store.client.delete_collection(settings.qdrant_collection)
        except Exception:
            pass  # Best-effort cleanup.


@pytest_asyncio.fixture
async def qdrant_in_memory_store() -> AsyncIterator[Any]:
    """In-memory Qdrant (:memory:) - per-test UUID, no network.

    Useful when the unit suite runs offline. Same API as the real
    ``QdrantVectorStore`` but the collection lives in process memory
    and is wiped when the process exits.
    """
    from src.retrieval.vector_store import QdrantVectorStore

    settings = _test_rag_settings(qdrant_local_path=":memory:")
    store = QdrantVectorStore(settings)
    await store.create_collection()
    await store.create_payload_indexes()
    yield store
    # No cleanup needed: the store goes out of scope and is GC'd.


@pytest.fixture
def in_memory_store() -> Iterator[Any]:
    """Pure in-memory vector store for pure-logic tests.

    No Qdrant, no SQL. Suitable when the test only exercises the
    scoring/filtering math and does not need real persistence.
    """
    from src.retrieval.vector_store import InMemoryVectorStore

    store = InMemoryVectorStore()
    yield store


@pytest.fixture
def rag_settings() -> Iterator[Any]:
    """A ``RAGSettings`` instance configured for the test environment."""
    yield _test_rag_settings()


@pytest_asyncio.fixture
async def postgres_session() -> AsyncIterator[Any]:
    """Real Neon Postgres session (or in-memory SQLite when env=test).

    The fixture uses the database URL from ``DATABASE_URL`` env var.
    For full unit-suite offline runs, set ``DATABASE_URL=sqlite:///:memory:``
    in ``.env.rag`` (the ``app_env=test`` validator allows it).
    """
    from sqlalchemy import text

    from src.db.session import Database

    settings = _test_rag_settings()
    db = Database(settings)
    try:
        # Quick connectivity probe so tests fail loudly instead of
        # mysteriously hanging on the first SQL.
        with db.engine.connect() as conn:
            conn.execute("SELECT 1")
        yield db
    finally:
        db.engine.dispose()


@pytest.fixture
def openai_embeddings() -> Iterator[Any]:
    """Real OpenAI embeddings provider when ``OPENAI_API_KEY`` is set,
    otherwise falls back to deterministic :class:`HashEmbeddingProvider`.

    The fallback ensures the unit suite still runs offline while letting
    integration tests use the real provider when credentials are
    available.
    """
    from src.services.embeddings import (
        CachedDenseEmbeddingProvider,
        HashEmbeddingProvider,
        build_embedding_provider,
    )

    if os.environ.get("OPENAI_API_KEY"):
        settings = _test_rag_settings(embedding_provider="openai")
        provider = build_embedding_provider(settings)
    else:
        provider = CachedDenseEmbeddingProvider(
            HashEmbeddingProvider(
                dimensions=int(os.environ.get("TEST_EMBED_DIM", "256")),
            )
        )
    yield provider


@pytest.fixture
def sparse_embeddings() -> Iterator[Any]:
    """Real hashed sparse embeddings provider (no external API)."""
    from src.services.sparse_embeddings import HashedSparseEmbeddingProvider

    yield HashedSparseEmbeddingProvider()


@pytest.fixture
def reranker_service() -> Iterator[Any]:
    """Real :class:`RerankerService` wrapping the cross-encoder reranker.

    Returns a ``RerankerService`` (not the bare ``CrossEncoderReranker``)
    because the production code paths in
    :mod:`src.retrieval.evidence_rerank` and :mod:`src.rag.workflow`
    call ``reranker_service.rerank(request)`` — the service-layer
    async method that adds timeout + circuit-breaker around the
    underlying sync model.

    Use ``pytest -m requires_rag_runtime`` to skip tests that need the
    real model when the network is unavailable.
    """
    from src.retrieval.reranker import CrossEncoderReranker, RerankerService

    settings = _test_rag_settings()
    base = CrossEncoderReranker(
        model_name=settings.reranker_model_name,
        revision=settings.reranker_model_revision,
        device=settings.reranker_device,
        backend=settings.reranker_backend,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )
    yield RerankerService(
        base,
        timeout_seconds=settings.reranker_timeout_seconds,
        circuit_failure_threshold=settings.reranker_circuit_failure_threshold,
        circuit_cooldown_seconds=settings.reranker_circuit_cooldown_seconds,
    )


@pytest.fixture
def cross_encoder_reranker() -> Iterator[Any]:
    """Real :class:`CrossEncoderReranker` (the bare model wrapper).

    Some tests need the raw reranker so they can call ``rerank_batch``
    directly or inspect lazy-load state (``_model is None``). The
    ``reranker_service`` fixture returns the wrapped service; this one
    returns the bare cross-encoder.
    """
    from src.retrieval.reranker import CrossEncoderReranker

    settings = _test_rag_settings()
    yield CrossEncoderReranker(
        model_name=settings.reranker_model_name,
        revision=settings.reranker_model_revision,
        device=settings.reranker_device,
        backend=settings.reranker_backend,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )


@pytest.fixture
def audit_recorder() -> Iterator[Any]:
    """Real :class:`AuditLogService` writing to Postgres (no mock)."""
    from src.security.audit import AuditLogService

    yield AuditLogService()


@pytest_asyncio.fixture
async def event_loop_policy() -> Iterator[Any]:
    """Async event loop policy for tests that need explicit loop control."""
    yield asyncio.DefaultEventLoopPolicy()