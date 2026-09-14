import os

# Force 32-dim embeddings for these tests (we build chunks with 32-dim
# vectors directly). Using setdefault is not enough because earlier
# tests in the same run may have already set TEST_EMBED_DIM to a
# different value, and pytest's module import order is not stable.
os.environ["TEST_EMBED_DIM"] = "32"

import uuid

import pytest
from qdrant_client.models import SparseVector

from src.domain.schemas import QdrantPayload, QdrantPointInput, SparseVectorData
from src.rag.config import RAGSettings
from src.retrieval.vector_store import (
    DENSE_VECTOR_NAME,
    PAYLOAD_INDEXES,
    SPARSE_VECTOR_NAME,
    QdrantVectorStore,
    VectorRecord,
)


def build_store() -> QdrantVectorStore:
    settings = RAGSettings(
        app_env="test",
        vector_backend="qdrant",
        qdrant_local_path=":memory:",
        qdrant_collection=f"test-{uuid.uuid4()}",
        embedding_dimensions=32,
    )
    return QdrantVectorStore(settings)


def build_chunk(*, version_id: str, chunk_id: str | None = None) -> QdrantPointInput:
    actual_chunk_id = chunk_id or str(uuid.uuid4())
    return QdrantPointInput(
        payload=QdrantPayload(
            tenant_id="hust",
            document_id=str(uuid.uuid4()),
            version_id=version_id,
            chunk_id=actual_chunk_id,
            parent_chunk_id=None,
            previous_chunk_id=None,
            next_chunk_id=None,
            owner_unit="TCCB",
            allowed_roles=["staff"],
            allowed_units=["TCCB"],
            classification="internal",
            status="published",
            valid_from="2026-01-01T00:00:00Z",
            valid_to=None,
            page=3,
            section="Điều 5",
            content_hash=f"sha256:{actual_chunk_id}",
            embedding_model="test-embedding",
            embedding_version="test-v1",
            sparse_model="hashed-lexical",
            sparse_version="test-v1",
            index_version="test-index-v1",
        ),
        dense_vector=[0.125] * 32,
        sparse_vector=SparseVectorData(indices=[10, 42], values=[0.7, 0.3]),
    )


@pytest.mark.asyncio
async def test_creates_named_vectors_and_payload_indexes(qdrant_in_memory_store):
    """Verify the in-memory store was initialised with named vectors and the payload
    indexes tracking set was populated.

    Note: in-memory Qdrant (``qdrant_local_path=":memory:"``) does not support
    server-side payload indexes - the ``create_payload_index`` calls are
    no-ops and the payload_schema comes back empty. We therefore verify
    intent via the store's internal ``_payload_indexes_created`` set,
    which is the same authoritative source the production code reads
    to decide whether to re-issue a create call.
    """
    store = qdrant_in_memory_store

    assert await store.collection_exists()

    # Named vectors
    info = await store.client.get_collection(store.collection)
    assert set(info.config.params.vectors) == {DENSE_VECTOR_NAME}
    assert info.config.params.vectors[DENSE_VECTOR_NAME].size == store.dimensions
    assert set(info.config.params.sparse_vectors) == {SPARSE_VECTOR_NAME}

    # The store's tracking set records every index the production code
    # attempted to create. This is what real (server) Qdrant would persist.
    assert store._payload_indexes_created == set(PAYLOAD_INDEXES)


def test_build_qdrant_point_contains_dense_sparse_and_complete_payload():
    store = build_store()
    chunk = build_chunk(version_id=str(uuid.uuid4()))

    point = store.build_qdrant_point(chunk)

    assert str(point.id) == chunk.payload.chunk_id
    assert set(point.vector) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}
    assert len(point.vector[DENSE_VECTOR_NAME]) == store.dimensions
    assert point.vector[SPARSE_VECTOR_NAME] == SparseVector(
        indices=[10, 42],
        values=[0.7, 0.3],
    )
    assert set(QdrantPayload.model_fields).issubset(point.payload)


@pytest.mark.asyncio
async def test_upsert_chunks_is_idempotent_for_stable_chunk_id(qdrant_in_memory_store):
    store = qdrant_in_memory_store
    chunk = build_chunk(version_id=str(uuid.uuid4()))

    await store.upsert_chunks([chunk])
    await store.upsert_chunks([chunk])

    count = await store.client.count(store.collection, exact=True)
    assert count.count == 1
    stored = await store.client.retrieve(
        collection_name=store.collection,
        ids=[chunk.payload.chunk_id],
        with_payload=True,
        with_vectors=True,
    )
    assert set(stored[0].vector) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}


@pytest.mark.asyncio
async def test_generic_upsert_creates_policy_payload_indexes(qdrant_in_memory_store):
    """``upsert`` must call ``create_payload_indexes`` and populate the tracking set."""
    store = qdrant_in_memory_store
    chunk = build_chunk(version_id=str(uuid.uuid4()))

    await store.upsert(
        [
            VectorRecord(
                id=chunk.payload.chunk_id,
                vector=chunk.dense_vector,
                payload=chunk.payload.model_dump(mode="json"),
            )
        ]
    )

    # The store tracks created indexes internally – no mocking needed
    assert store._payload_indexes_created == set(PAYLOAD_INDEXES)


@pytest.mark.asyncio
async def test_generic_upsert_promotes_sparse_payload_to_named_vector(
    qdrant_in_memory_store,
):
    store = qdrant_in_memory_store
    chunk = build_chunk(version_id=str(uuid.uuid4()))
    payload = chunk.payload.model_dump(mode="json")
    payload["sparse_vector"] = {
        "indices": chunk.sparse_vector.indices,
        "values": chunk.sparse_vector.values,
    }

    await store.upsert(
        [VectorRecord(id=chunk.payload.chunk_id, vector=chunk.dense_vector, payload=payload)]
    )
    [stored] = await store.client.retrieve(
        collection_name=store.collection,
        ids=[chunk.payload.chunk_id],
        with_payload=True,
        with_vectors=True,
    )

    assert set(stored.vector) == {DENSE_VECTOR_NAME, SPARSE_VECTOR_NAME}
    assert "sparse_vector" not in stored.payload


@pytest.mark.asyncio
async def test_delete_version_points_does_not_affect_other_versions(
    qdrant_in_memory_store,
):
    store = qdrant_in_memory_store
    first_version = str(uuid.uuid4())
    second_version = str(uuid.uuid4())
    first_chunk = build_chunk(version_id=first_version)
    second_chunk = build_chunk(version_id=second_version)
    await store.upsert_chunks([first_chunk, second_chunk])

    await store.delete_version_points(first_version, tenant_id="hust")

    remaining, _ = await store.client.scroll(
        collection_name=store.collection,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    assert [point.payload["version_id"] for point in remaining] == [second_version]
    assert str(remaining[0].id) == second_chunk.payload.chunk_id


def test_build_qdrant_point_rejects_wrong_dense_dimension():
    store = build_store()
    chunk = build_chunk(version_id=str(uuid.uuid4()))
    invalid = chunk.model_copy(update={"dense_vector": [0.1, 0.2]})

    with pytest.raises(ValueError, match="collection requires 32"):
        store.build_qdrant_point(invalid)
