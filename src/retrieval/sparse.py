from __future__ import annotations

from typing import Protocol

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.domain.schemas import Candidate, QdrantPayload, SparseVectorData
from src.retrieval.dense import ChunkContentProvider
from src.retrieval.query_transform import validate_query
from src.security.metadata_contract import metadata_consistency_errors
from src.services.sparse_embeddings import SparseEmbeddingProvider


class SparseSearchStore(Protocol):
    async def search_sparse(
        self,
        query_vector: SparseVectorData,
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]: ...


def _build_sparse_filter(
    access_filter: Filter,
    *,
    index_version: str,
    sparse_model: str,
    sparse_version: str,
) -> Filter:
    return Filter(
        must=[
            access_filter,
            FieldCondition(
                key="index_version",
                match=MatchValue(value=index_version),
            ),
            FieldCondition(
                key="sparse_model",
                match=MatchValue(value=sparse_model),
            ),
            FieldCondition(
                key="sparse_version",
                match=MatchValue(value=sparse_version),
            ),
        ]
    )


async def sparse_search(
    query: str,
    access_filter: Filter,
    limit: int,
    index_version: str,
    *,
    embedding_provider: SparseEmbeddingProvider,
    vector_store: SparseSearchStore,
    content_provider: ChunkContentProvider,
) -> list[Candidate]:
    validate_query(query)
    if access_filter is None:
        raise ValueError("access_filter is required for sparse retrieval.")
    if not 1 <= limit <= 100:
        raise ValueError("Sparse retrieval limit must be between 1 and 100.")
    if not index_version.strip():
        raise ValueError("index_version must not be blank.")

    query_vector = embedding_provider.sparse_embed_query(query)
    query_filter = _build_sparse_filter(
        access_filter,
        index_version=index_version,
        sparse_model=embedding_provider.model_name,
        sparse_version=embedding_provider.model_version,
    )
    results = await vector_store.search_sparse(
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
    for sparse_rank, (chunk_id, score, raw_payload) in enumerate(results, start=1):
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
                metadata={**raw_payload, "sparse_score": score},
                dense_rank=None,
                sparse_rank=sparse_rank,
                fusion_score=0.0,
                rerank_score=None,
            )
        )
    return candidates


class SparseRetriever:
    def __init__(
        self,
        embedding_provider: SparseEmbeddingProvider,
        vector_store: SparseSearchStore,
        content_provider: ChunkContentProvider,
    ):
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.content_provider = content_provider

    async def sparse_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]:
        return await sparse_search(
            query,
            access_filter,
            limit,
            index_version,
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
            content_provider=self.content_provider,
        )
