import os
import uuid
import warnings

# Force 32-dim embeddings BEFORE importing anything that reads the env.
os.environ.setdefault("TEST_EMBED_DIM", "32")

import pytest

from src.domain.schemas import QdrantPayload, QdrantPointInput, SparseVectorData
from src.rag.config import RAGSettings
from src.retrieval.sparse import SparseRetriever
from src.retrieval.vector_store import QdrantVectorStore
from src.security.policy import AuthenticatedIdentity, build_access_filter, build_user_context
from src.services.sparse_embeddings import (
    HashedSparseEmbeddingProvider,
    tokenize_sparse,
)


# ---------------------------------------------------------------------------
# Test fixtures - real implementations, no mocks
# ---------------------------------------------------------------------------


class InMemoryContentRepository:
    """Real content provider (in-memory dict, no DB).

    Mirrors the protocol expected by :class:`SparseRetriever`. The class
    is not a mock - it is the production storage backend when running
    offline. Each test gets a fresh instance via the fixture.
    """

    def __init__(self, contents: dict[str, str] | None = None) -> None:
        self._contents = dict(contents or {})
        self.requested_ids: list[str] = []

    def get_chunk_contents(self, chunk_ids: list[str]) -> dict[str, str]:
        self.requested_ids.extend(chunk_ids)
        return {
            chunk_id: self._contents[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self._contents
        }


# Match the dimension expected by the qdrant_in_memory_store fixture
# (controlled by TEST_EMBED_DIM, defaulting to 32 here).
EMBED_DIM = int(os.environ["TEST_EMBED_DIM"])


@pytest.fixture
def embedding_provider():
    """Real deterministic :class:`HashedSparseEmbeddingProvider` (no API calls)."""
    return HashedSparseEmbeddingProvider(model_version="sparse-v1")


@pytest.fixture
def qdrant_store(qdrant_in_memory_store):
    """Real :class:`QdrantVectorStore` configured for these tests."""
    return qdrant_in_memory_store


def make_payload(**overrides) -> QdrantPayload:
    values = {
        "tenant_id": "tenant-a",
        "document_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
        "chunk_id": str(uuid.uuid4()),
        "parent_chunk_id": None,
        "previous_chunk_id": None,
        "next_chunk_id": None,
        "owner_unit": "UNIT-A",
        "allowed_roles": ["staff"],
        "allowed_units": ["UNIT-A"],
        "classification": "internal",
        "status": "published",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "page": 1,
        "section": "Điều 1",
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "embedding_model": "dense-test-model",
        "embedding_version": "dense-v1",
        "sparse_model": "hashed-lexical",
        "sparse_version": "sparse-v1",
        "index_version": "index-v5",
    }
    values.update(overrides)
    return QdrantPayload.model_validate(values)


def make_point(
    payload: QdrantPayload,
    sparse_vector: SparseVectorData,
) -> QdrantPointInput:
    return QdrantPointInput(
        payload=payload,
        dense_vector=[0.125] * EMBED_DIM,
        sparse_vector=sparse_vector,
    )


def make_user():
    return build_user_context(
        AuthenticatedIdentity(
            user_id="user-1",
            tenant_id="tenant-a",
            department="UNIT-A",
            assigned_roles=frozenset({"staff"}),
        )
    )


def test_sparse_tokenizer_keeps_exact_identifier_tokens():
    tokens = tokenize_sparse(
        "Tra cứu QT-TC-003, Quyết định 123/QĐ-CT và Mẫu 04."
    )
    assert "QT-TC-003" in tokens
    assert "123/QĐ-CT" in tokens
    assert "Mẫu 04" in tokens


def test_sparse_provider_supports_document_batch_embedding():
    provider = HashedSparseEmbeddingProvider(model_version="sparse-v1")
    vectors = provider.sparse_embed_documents(
        ["QT-TC-003", "123/QĐ-CT", "Mẫu 04"]
    )
    assert len(vectors) == 3
    assert all(vector.indices and vector.values for vector in vectors)


@pytest.mark.asyncio
async def test_keyword_heavy_queries_rank_expected_document_and_enforce_filter(
    qdrant_store,
    embedding_provider,
):
    documents = {
        "procedure": "Quy trình QT-TC-003 hướng dẫn tuyển dụng viên chức.",
        "decision": "Quyết định 123/QĐ-CT quy định chế độ công tác.",
        "form": "Mẫu 04 dùng để đăng ký xác nhận sinh viên.",
        "unit": "Phòng Công tác Sinh viên tiếp nhận hồ sơ học bổng.",
        "phrase": "Chính sách miễn giảm học phí sau đại học.",
        "distractor": "Thông báo lịch nghỉ hè dành cho giảng viên.",
        "cross_tenant": (
            "QT-TC-003 123/QĐ-CT Mẫu 04 Phòng Công tác Sinh viên "
            "miễn giảm học phí sau đại học"
        ),
    }
    payloads = {
        key: make_payload(tenant_id="tenant-b" if key == "cross_tenant" else "tenant-a")
        for key in documents
    }
    points = [
        make_point(
            payloads[key],
            embedding_provider.sparse_embed_query(content),
        )
        for key, content in documents.items()
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        await qdrant_store.upsert_chunks(points)

    content_repository = InMemoryContentRepository(
        {payloads[key].chunk_id: content for key, content in documents.items()}
    )
    retriever = SparseRetriever(embedding_provider, qdrant_store, content_repository)
    access_filter = build_access_filter(make_user())

    cases = {
        "QT-TC-003": "procedure",
        "123/QĐ-CT": "decision",
        "Mẫu 04": "form",
        "Phòng Công tác Sinh viên": "unit",
        "miễn giảm học phí sau đại học": "phrase",
    }
    for query, expected_key in cases.items():
        candidates = await retriever.sparse_search(
            query,
            access_filter,
            limit=10,
            index_version="index-v5",
        )
        returned_ids = [candidate.chunk_id for candidate in candidates]
        assert payloads[expected_key].chunk_id in returned_ids[:10]
        assert payloads["cross_tenant"].chunk_id not in returned_ids
        assert all(candidate.sparse_rank is not None for candidate in candidates)
        assert all(candidate.dense_rank is None for candidate in candidates)
        assert all(candidate.metadata["tenant_id"] == "tenant-a" for candidate in candidates)
        assert all("sparse_score" in candidate.metadata for candidate in candidates)


@pytest.mark.asyncio
async def test_sparse_search_requires_access_filter(embedding_provider, qdrant_store):
    retriever = SparseRetriever(embedding_provider, qdrant_store, InMemoryContentRepository({}))

    with pytest.raises(ValueError, match="access_filter is required"):
        await retriever.sparse_search(
            "QT-TC-003",
            None,
            limit=10,
            index_version="index-v5",
        )
