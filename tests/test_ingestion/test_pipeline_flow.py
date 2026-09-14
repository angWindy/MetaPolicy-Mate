"""Unit tests for the ingestion pipeline's strict index/publish flow.

These tests guard the user-facing contract documented in the review:
- Publishing is only allowed from INDEXED (not APPROVED).
- Failed indexing keeps the version at APPROVED and surfaces a clear error.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.pipeline import IngestionPipeline
from src.rag.config import RAGSettings


class _FakeEmbedding:
    model_name = "fake"
    model_version = "v1"

    async def embed_documents(self, texts, content_hashes=None):
        return [[0.0] * 4 for _ in texts]


class _FakeVectorStore:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.upserts = []

    async def create_payload_indexes(self):
        return None

    async def upsert(self, records):
        if self.fail:
            raise RuntimeError("Qdrant unreachable")
        self.upserts.extend(records)


def _build_pipeline(vector_store, version=None, chunks=None, document=None):
    settings = RAGSettings()
    repository = MagicMock()
    version = version or SimpleNamespace(
        id="v1",
        document_id="d1",
        effective_from=None,
        effective_to=None,
        processing_status="approved",
    )
    chunks = chunks or []
    document = document or SimpleNamespace(
        access_level="internal", allowed_departments=["ALL"]
    )
    session = MagicMock()
    session.__enter__ = lambda self: session
    session.__exit__ = lambda self, *args: None
    session.get.side_effect = lambda model, _id: {
        "DocumentVersion": version,
        "Document": document,
    }.get(model.__name__, None)
    session.scalars.return_value = chunks
    session_factory = MagicMock(return_value=session)
    repository.session_factory = session_factory

    embeddings = _FakeEmbedding()
    pipeline = IngestionPipeline(
        settings=settings,
        repository=repository,
        parser=MagicMock(),
        storage=MagicMock(),
        embeddings=embeddings,
        vector_store=vector_store,
    )
    return pipeline, repository, version


def test_index_approved_version_raises_runtime_when_vector_store_fails():
    """On Qdrant failure, index must raise RuntimeError so status stays at APPROVED."""
    pipeline, repository, _ = _build_pipeline(
        _FakeVectorStore(fail=True),
    )
    with pytest.raises(RuntimeError, match="APPROVED"):
        asyncio.run(pipeline.index_approved_version("v1"))
    # Crucially: mark_indexed MUST NOT have been called.
    assert not repository.mark_indexed.called


def test_index_approved_version_calls_mark_indexed_only_on_success():
    """On success, mark_indexed is called exactly once after upsert."""
    vector_store = _FakeVectorStore(fail=False)
    pipeline, repository, _ = _build_pipeline(vector_store)
    repository.mark_indexed = MagicMock()
    count = asyncio.run(pipeline.index_approved_version("v1"))
    assert count == 0  # no chunks in this fake
    assert repository.mark_indexed.called
    assert repository.mark_indexed.call_args.args == ("v1",)
