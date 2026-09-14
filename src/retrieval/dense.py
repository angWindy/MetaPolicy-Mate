from __future__ import annotations

from typing import Protocol

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.domain.schemas import Candidate, QdrantPayload
from src.retrieval.query_transform import validate_query
from src.security.metadata_contract import metadata_consistency_errors
from src.services.embeddings import (
    DenseEmbeddingProvider,
    validate_embedding_dimension,
)


class DenseSearchStore(Protocol):
    dimensions: int

    async def search(
        self,
        query_vector: list[float],
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]: ...


class ChunkContentProvider(Protocol):
    def get_chunk_contents(self, chunk_ids: list[str]) -> dict[str, str]: ...

    def get_chunk_index_metadata(
        self, chunk_ids: list[str], *, index_version: str
    ) -> dict[str, dict]: ...


def _build_dense_filter(
    access_filter: Filter,
    *,
    index_version: str,
    embedding_model: str,
    embedding_version: str,
) -> Filter:
    return Filter(
        must=[
            access_filter,
            FieldCondition(
                key="index_version",
                match=MatchValue(value=index_version),
            ),
            FieldCondition(
                key="embedding_model",
                match=MatchValue(value=embedding_model),
            ),
            FieldCondition(
                key="embedding_version",
                match=MatchValue(value=embedding_version),
            ),
        ]
    )


async def dense_search(
    query: str,
    access_filter: Filter,
    limit: int,
    index_version: str,
    *,
    embedding_provider: DenseEmbeddingProvider,
    vector_store: DenseSearchStore,
    content_provider: ChunkContentProvider,
) -> list[Candidate]:
    validate_query(query)
    if access_filter is None:
        raise ValueError("access_filter is required for dense retrieval.")
    if not 1 <= limit <= 100:
        raise ValueError("Dense retrieval limit must be between 1 and 100.")
    if not index_version.strip():
        raise ValueError("index_version must not be blank.")
    if embedding_provider.dimensions and vector_store.dimensions:
        if embedding_provider.dimensions != vector_store.dimensions:
            raise ValueError(
                f"Provider dimension {embedding_provider.dimensions} does not match "
                f"Qdrant dimension {vector_store.dimensions}."
            )

    query_vector = await embedding_provider.embed_query(query)
    if vector_store.dimensions:
        validate_embedding_dimension(query_vector, vector_store.dimensions)
    query_filter = _build_dense_filter(
        access_filter,
        index_version=index_version,
        embedding_model=embedding_provider.model_name,
        embedding_version=embedding_provider.model_version,
    )
    results = await vector_store.search(
        query_vector,
        limit=limit,
        query_filter=query_filter,
    )
    result_ids = [chunk_id for chunk_id, _score, _payload in results]
    contents = content_provider.get_chunk_contents(result_ids)
    authoritative_metadata = content_provider.get_chunk_index_metadata(
        result_ids, index_version=index_version
    )

    candidates: list[Candidate] = []
    for dense_rank, (chunk_id, score, raw_payload) in enumerate(results, start=1):
        payload = QdrantPayload.model_validate(raw_payload)
        if payload.chunk_id != chunk_id:
            raise ValueError("Qdrant point ID does not match payload chunk_id.")
        postgres_payload = authoritative_metadata.get(chunk_id)
        if (
            chunk_id not in contents
            or postgres_payload is None
            or metadata_consistency_errors(postgres_payload, raw_payload)
        ):
            continue
        candidates.append(
            Candidate(
                chunk_id=chunk_id,
                document_id=payload.document_id,
                version_id=payload.version_id,
                content=contents[chunk_id],
                metadata={**raw_payload, "dense_score": score},
                dense_rank=dense_rank,
                sparse_rank=None,
                fusion_score=0.0,
                rerank_score=None,
            )
        )
    return candidates


class DenseRetriever:
    def __init__(
        self,
        embedding_provider: DenseEmbeddingProvider,
        vector_store: DenseSearchStore,
        content_provider: ChunkContentProvider,
    ):
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.content_provider = content_provider

    async def dense_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]:
        return await dense_search(
            query,
            access_filter,
            limit,
            index_version,
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
            content_provider=self.content_provider,
        )
