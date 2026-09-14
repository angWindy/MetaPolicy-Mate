from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from src.domain.schemas import QdrantPointInput, SparseVectorData
from src.rag.config import RAGSettings

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Filter, PointStruct, UpdateResult


DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

PAYLOAD_INDEXES = {
    "tenant_id": "keyword",
    "document_id": "keyword",
    "version_id": "keyword",
    "chunk_id": "keyword",
    "parent_chunk_id": "keyword",
    "owner_unit": "keyword",
    "allowed_roles": "keyword",
    "allowed_units": "keyword",
    "classification": "keyword",
    "status": "keyword",
    "legal_status": "keyword",
    "valid_from": "datetime",
    "valid_to": "datetime",
    "page": "integer",
    "section": "keyword",
    "content_hash": "keyword",
    "embedding_model": "keyword",
    "embedding_version": "keyword",
    "sparse_model": "keyword",
    "sparse_version": "keyword",
    "index_version": "keyword",
}


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    payload: dict


class VectorStore(Protocol):
    async def upsert(self, records: list[VectorRecord]) -> None: ...

    async def search(
        self,
        query_vector: list[float],
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]: ...

    async def search_sparse(
        self,
        query_vector: SparseVectorData,
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]: ...

    async def create_payload_indexes(self) -> None: ...


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


class InMemoryVectorStore:
    def __init__(self):
        self.records: dict[str, VectorRecord] = {}
        self._sparse_indices: dict[str, dict[int, float]] = {}

    async def create_payload_indexes(self) -> None:
        """No-op for in-memory mode; payload filtering happens at the caller."""
        return None

    async def upsert(self, records: list[VectorRecord]) -> None:
        for record in records:
            self.records[record.id] = record
            sparse = record.payload.get("sparse_vector")
            if isinstance(sparse, dict) and "indices" in sparse and "values" in sparse:
                indices = sparse.get("indices") or []
                values = sparse.get("values") or []
                self._sparse_indices[record.id] = {
                    int(idx): float(val) for idx, val in zip(indices, values, strict=True)
                }

    async def search(
        self,
        query_vector: list[float],
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]:
        # PostgreSQL-derived allowed_ids remain the pre-filter in memory mode.
        scored = []
        for record in self.records.values():
            if allowed_ids is not None and record.id not in allowed_ids:
                continue
            scored.append(
                (
                    record.id,
                    cosine_similarity(query_vector, record.vector),
                    record.payload,
                )
            )
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    async def search_sparse(
        self,
        query_vector: SparseVectorData,
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]:
        from qdrant_client.models import Filter, HasIdCondition

        if allowed_ids is not None and not allowed_ids:
            return []
        if allowed_ids is not None:
            id_condition = HasIdCondition(has_id=list(allowed_ids))
            query_filter = (
                Filter(must=[query_filter, id_condition])
                if query_filter is not None
                else Filter(must=[id_condition])
            )
        del query_filter  # in-memory mode applies allowed_ids only
        scored: list[tuple[str, float, dict]] = []
        for chunk_id, vector in self._sparse_indices.items():
            if allowed_ids is not None and chunk_id not in allowed_ids:
                continue
            score = sum(
                weight * vector.get(int(idx), 0.0)
                for idx, weight in zip(query_vector.indices, query_vector.values, strict=True)
            )
            record = self.records.get(chunk_id)
            if record is None:
                continue
            scored.append((chunk_id, score, record.payload))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


class QdrantVectorStore:
    def __init__(
        self,
        settings: RAGSettings,
        client: AsyncQdrantClient | None = None,
    ):
        from qdrant_client import AsyncQdrantClient

        self.collection = settings.qdrant_collection
        self.dimensions = settings.embedding_dimensions
        self._payload_indexes_created: set[str] = set()
        if client is not None:
            self.client = client
        elif settings.qdrant_local_path == ":memory:":
            self.client = AsyncQdrantClient(location=":memory:")
        elif settings.qdrant_local_path:
            self.client = AsyncQdrantClient(path=settings.qdrant_local_path)
        else:
            self.client = AsyncQdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )

    async def collection_exists(self) -> bool:
        return await self.client.collection_exists(self.collection)

    async def create_collection(self) -> None:
        from qdrant_client.models import (
            Distance,
            SparseIndexParams,
            SparseVectorParams,
            VectorParams,
        )

        if await self.collection_exists():
            return
        await self.client.create_collection(
            collection_name=self.collection,
            vectors_config={
                DENSE_VECTOR_NAME: VectorParams(
                    size=self.dimensions,
                    distance=Distance.COSINE,
                )
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: SparseVectorParams(
                    index=SparseIndexParams(on_disk=False),
                )
            },
        )

    async def create_payload_indexes(self) -> None:
        from qdrant_client.models import PayloadSchemaType

        await self.create_collection()
        collection = await self.client.get_collection(self.collection)
        existing_indexes = set(collection.payload_schema) | self._payload_indexes_created
        for field_name, schema_name in PAYLOAD_INDEXES.items():
            if field_name in existing_indexes:
                continue
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field_name,
                field_schema=PayloadSchemaType(schema_name),
                wait=True,
            )
            self._payload_indexes_created.add(field_name)

    async def ensure_collection(self) -> None:
        await self.create_collection()

    def build_qdrant_point(self, chunk: QdrantPointInput) -> PointStruct:
        from qdrant_client.models import PointStruct, SparseVector

        if len(chunk.dense_vector) != self.dimensions:
            raise ValueError(
                f"Dense vector has {len(chunk.dense_vector)} dimensions; "
                f"collection requires {self.dimensions}."
            )
        return PointStruct(
            id=chunk.payload.chunk_id,
            vector={
                DENSE_VECTOR_NAME: chunk.dense_vector,
                SPARSE_VECTOR_NAME: SparseVector(
                    indices=chunk.sparse_vector.indices,
                    values=chunk.sparse_vector.values,
                ),
            },
            payload=chunk.payload.model_dump(mode="json"),
        )

    async def upsert_chunks(self, chunks: list[QdrantPointInput]) -> None:
        await self.create_collection()
        await self.create_payload_indexes()
        if not chunks:
            return
        await self.client.upsert(
            collection_name=self.collection,
            points=[self.build_qdrant_point(chunk) for chunk in chunks],
            wait=True,
        )

    async def delete_version_points(
        self,
        version_id: str,
        *,
        tenant_id: str | None = None,
    ) -> UpdateResult | None:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        if not version_id.strip():
            raise ValueError("version_id must not be blank.")
        if not await self.collection_exists():
            return None
        # Ensure payload indexes exist before issuing the delete filter.
        # ``version_id`` is filtered as a keyword match; without an index
        # Qdrant returns a 400 ("Index required but not found"). The
        # upsert path also calls create_payload_indexes, but on the
        # first ingest a previous version's points may have been
        # written without indexes and the delete runs first.
        await self.create_payload_indexes()
        conditions = [
            FieldCondition(key="version_id", match=MatchValue(value=version_id)),
        ]
        if tenant_id is not None:
            if not tenant_id.strip():
                raise ValueError("tenant_id must not be blank.")
            conditions.append(
                FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))
            )
        return await self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(filter=Filter(must=conditions)),
            wait=True,
        )

    async def delete_document_points(
        self,
        document_id: str,
        *,
        tenant_id: str | None = None,
    ) -> int:
        """Last-mile cleanup for a document.

        Removes any points whose ``document_id`` matches the supplied
        value (optionally scoped by ``tenant_id``). Used by the admin
        cascade-delete flow to catch chunks that lost their version_id
        between ingest and delete. Returns the number of points removed
        (best-effort — Qdrant's HTTP delete API does not return a count,
        so we report ``0`` and let the caller log success via the
        ``delete_version_points`` totals).
        """
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        if not document_id.strip():
            raise ValueError(
                "document_id must not be blank."
            )
        if not await self.collection_exists():
            return 0
        conditions = [
            FieldCondition(
                key="document_id",
                match=MatchValue(value=document_id),
            ),
        ]
        if tenant_id is not None:
            if not tenant_id.strip():
                raise ValueError(
                    "tenant_id must not be blank."
                )
            conditions.append(
                FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=tenant_id),
                )
            )
        await self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(must=conditions)
            ),
            wait=True,
        )
        return 0

    async def upsert(self, records: list[VectorRecord]) -> None:
        """Batch-upsert records so the per-request payload stays under 32 MiB."""
        from qdrant_client.models import PointStruct, SparseVector

        if not records:
            return
        await self.create_payload_indexes()
        # 32 MiB is the documented Qdrant HTTP ceiling; budget ~24 MiB to
        # leave room for HTTP/JSON framing overhead.
        batch_bytes = 24 * 1024 * 1024
        points = []
        for record in records:
            payload = dict(record.payload)
            sparse_payload = payload.pop("sparse_vector", None)
            vectors: dict = {DENSE_VECTOR_NAME: record.vector}
            if isinstance(sparse_payload, dict):
                indices = sparse_payload.get("indices") or []
                values = sparse_payload.get("values") or []
                if indices and len(indices) == len(values):
                    vectors[SPARSE_VECTOR_NAME] = SparseVector(
                        indices=[int(value) for value in indices],
                        values=[float(value) for value in values],
                    )
            points.append(PointStruct(id=record.id, vector=vectors, payload=payload))

        def _payload_bytes(batch: list[PointStruct]) -> int:
            import json as _json

            try:
                return len(
                    _json.dumps(
                        [
                            {
                                "id": str(p.id),
                                "vector": p.vector,
                                "payload": p.payload,
                            }
                            for p in batch
                        ],
                        default=str,
                    ).encode("utf-8")
                )
            except Exception:  # noqa: BLE001 - rough size estimate only
                return 0

        batch: list[PointStruct] = []
        used = 0
        for point in points:
            cost = max(_payload_bytes([point]), 1)
            if batch and used + cost > batch_bytes:
                await self.client.upsert(
                    collection_name=self.collection,
                    points=batch,
                    wait=True,
                )
                batch = []
                used = 0
            batch.append(point)
            used += cost
        if batch:
            await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                wait=True,
            )

    async def search(
        self,
        query_vector: list[float],
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]:
        from qdrant_client.models import Filter, HasIdCondition

        await self.ensure_collection()
        if allowed_ids is not None:
            if not allowed_ids:
                return []
            id_condition = HasIdCondition(has_id=list(allowed_ids))
            query_filter = (
                Filter(must=[query_filter, id_condition])
                if query_filter is not None
                else Filter(must=[id_condition])
            )
        results = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [(str(point.id), float(point.score), dict(point.payload or {})) for point in results.points]

    async def search_sparse(
        self,
        query_vector: SparseVectorData,
        limit: int,
        allowed_ids: set[str] | None = None,
        query_filter: Filter | None = None,
    ) -> list[tuple[str, float, dict]]:
        from qdrant_client.models import Filter, HasIdCondition, SparseVector

        await self.ensure_collection()
        if allowed_ids is not None:
            if not allowed_ids:
                return []
            id_condition = HasIdCondition(has_id=list(allowed_ids))
            query_filter = (
                Filter(must=[query_filter, id_condition])
                if query_filter is not None
                else Filter(must=[id_condition])
            )
        results = await self.client.query_points(
            collection_name=self.collection,
            query=SparseVector(
                indices=query_vector.indices,
                values=query_vector.values,
            ),
            using=SPARSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            (str(point.id), float(point.score), dict(point.payload or {}))
            for point in results.points
        ]


def build_vector_store(settings: RAGSettings, dimensions: int) -> VectorStore:
    if settings.vector_backend == "qdrant":
        return QdrantVectorStore(settings)
    return InMemoryVectorStore()
