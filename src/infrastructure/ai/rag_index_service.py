import hashlib

from datetime import (
    datetime,
    time,
    timezone,
)
from uuid import (
    UUID,
    uuid5,
)

from sqlalchemy import (
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from src.application.common.interfaces.rag_index_service import (
    RagIndexService,
)
from src.config import Settings
from src.domain.entities.document import (
    Document,
)
from src.domain.entities.document_chunk import (
    DocumentChunk,
)
from src.domain.entities.document_version import (
    DocumentVersion,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)

from src.infrastructure.ai.rag_runtime import (
    get_p234_rag_runtime,
)

from src.domain.schemas import (
    QdrantPayload,
    QdrantPointInput,
)
from src.retrieval.vector_store import (
    InMemoryVectorStore,
    QdrantVectorStore,
    VectorRecord,
)
from src.persistence.tenant.models.department import (
    DepartmentModel,
)
from src.persistence.tenant.models.document import (
    DocumentModel,
)
from src.persistence.tenant.models.document_chunk import (
    DocumentChunkModel,
)
from src.persistence.tenant.models.document_department import (
    DocumentDepartmentModel,
)
from src.persistence.tenant.models.document_section import (
    DocumentSectionModel,
)
from src.persistence.tenant.models.document_section_version import (
    DocumentSectionVersionModel,
)
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)


def build_section_version_point_id(
    section_version_id: UUID,
) -> str:
    return str(
        uuid5(
            section_version_id,
            "p234-rag-section-version",
        )
    )

class AiRagIndexService(
    RagIndexService
):
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
    ) -> None:
        self._settings = settings
        self._session = session

    @staticmethod
    def _normalize_units(
        *,
        access_scope: (
            DocumentAccessScope
        ),
        allowed_units: list[str],
    ) -> list[str]:
        if (
            access_scope
            == DocumentAccessScope.PUBLIC
        ):
            return ["*"]

        units = list(
            dict.fromkeys(
                item.strip().upper()
                for item in allowed_units
                if item.strip()
            )
        )

        if not units:
            raise ValueError(
                "Department-restricted "
                "document requires at "
                "least one allowed unit."
            )

        return units

    @staticmethod
    def _classification(
        access_scope: (
            DocumentAccessScope
        ),
    ) -> str:
        if (
            access_scope
            == DocumentAccessScope.PUBLIC
        ):
            return "public"

        return "internal"

    @staticmethod
    def _page(
        metadata: dict,
    ) -> int | None:
        value = metadata.get(
            "page"
        )

        if isinstance(
            value,
            int,
        ) and value >= 1:
            return value

        return None

    @staticmethod
    def _section(
        metadata: dict,
    ) -> str | None:
        value = (
            metadata.get("section")
            or metadata.get("heading")
            or metadata.get(
                "article"
            )
        )

        if value is None:
            return None

        value = str(
            value
        ).strip()

        return value or None

    async def _upsert_points(
        self,
        points: list[
            QdrantPointInput
        ],
    ) -> None:
        if not points:
            return

        runtime = (
            get_p234_rag_runtime()
        )

        vector_store = (
            runtime.vector_store
        )

        if isinstance(
            vector_store,
            QdrantVectorStore,
        ):
            await (
                vector_store
                .upsert_chunks(
                    points
                )
            )

            return

        if isinstance(
            vector_store,
            InMemoryVectorStore,
        ):
            records: list[
                VectorRecord
            ] = []

            for point in points:
                payload = (
                    point.payload
                    .model_dump(
                        mode="json"
                    )
                )

                payload[
                    "sparse_vector"
                ] = (
                    point.sparse_vector
                    .model_dump(
                        mode="json"
                    )
                )

                records.append(
                    VectorRecord(
                        id=(
                            point
                            .payload
                            .chunk_id
                        ),
                        vector=(
                            point
                            .dense_vector
                        ),
                        payload=payload,
                    )
                )

            await (
                vector_store
                .upsert(
                    records
                )
            )

            return

        raise RuntimeError(
            "Unsupported vector store."
        )

    async def index_chunks(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        chunks: list[DocumentChunk],
        allowed_units: list[str],
        tenant_id: str | None = None,
    ) -> None:
        if not chunks:
            return

        runtime = (
            get_p234_rag_runtime()
        )

        units = self._normalize_units(
            access_scope=(
                document.access_scope
            ),
            allowed_units=(
                allowed_units
            ),
        )

        classification = (
            self._classification(
                document.access_scope
            )
        )

        owner_unit = (
            "PUBLIC"
            if (
                document.access_scope
                == (
                    DocumentAccessScope
                    .PUBLIC
                )
            )
            else units[0]
        )

        # Resolve tenant_id for the Qdrant payload. Historically this
        # came from ``settings.school_code`` (a hardcoded
        # ``P234-DEMO`` constant) and propagated to every chunk as a
        # single bogus namespace. That const has been removed: tenant
        # identity now comes from the document itself.
        #
        # Resolution rules (first hit wins):
        #   1. Explicit ``tenant_id`` argument — callers that know the
        #      owning school (the upload handler) pass it explicitly.
        #   2. ``"public"`` for PUBLIC-scope documents — the retrieval
        #      filter treats ``"public"`` as a wildcard so any
        #      authenticated user can search public chunks regardless of
        #      their department.
        #   3. The first ``allowed_units`` entry lowercased — for
        #      DEPARTMENT-bound documents the owning school IS the
        #      first allowed unit. Lowercased for consistency with
        #      ``update_document_access`` and ``reindex_section``
        #      (both use ``units[0].lower()``), and to match the
        #      ``actor.department.lower()`` convention used on the
        #      retrieval side.
        #   4. Fallback to ``"public"`` — defensive; should not occur
        #      for well-formed DEPARTMENT documents.
        resolved_tenant_id = (
            tenant_id
            or (
                "public"
                if (
                    document.access_scope
                    == DocumentAccessScope.PUBLIC
                )
                else (
                    units[0].lower()
                    if units
                    else "public"
                )
            )
        )

        embedding_texts = [
            chunk.embedding_text
            for chunk in chunks
        ]

        content_hashes = [
            chunk.content_hash
            for chunk in chunks
        ]

        dense_vectors = await (
            runtime.embeddings
            .embed_documents(
                embedding_texts,
                content_hashes=(
                    content_hashes
                ),
            )
        )

        sparse_vectors = (
            runtime.sparse_provider
            .sparse_embed_documents(
                embedding_texts
            )
        )

        if (
            len(dense_vectors)
            != len(chunks)
            or len(sparse_vectors)
            != len(chunks)
        ):
            raise RuntimeError(
                "Embedding result count "
                "does not match chunk count."
            )

        valid_from = (
            datetime.combine(
                document.effective_date,
                time.min,
                tzinfo=timezone.utc,
            )
        )

        points: list[
            QdrantPointInput
        ] = []

        for (
            chunk,
            dense_vector,
            sparse_vector,
        ) in zip(
            chunks,
            dense_vectors,
            sparse_vectors,
            strict=True,
        ):
            metadata = dict(
                chunk.metadata or {}
            )

            payload = QdrantPayload(
                tenant_id=(
                    resolved_tenant_id
                ),
                document_id=str(
                    document.id
                ),
                version_id=str(
                    version.id
                ),
                chunk_id=str(
                    chunk.id
                ),
                owner_unit=(
                    owner_unit
                ),

                # QUAN TRỌNG:
                # Không dùng ["*"] ở đây.
                # Nếu DEPARTMENT mà
                # allowed_roles=["*"] thì
                # filter AI cũ sẽ cho mọi
                # role đi qua.
                allowed_roles=[],

                allowed_units=units,

                classification=(
                    classification
                ),

                # Qdrant chỉ là index.
                # Candidate nào thực sự
                # được dùng vẫn do Neon BE
                # whitelist ở A-06.
                status="published",

                valid_from=valid_from,
                valid_to=None,

                page=self._page(
                    metadata
                ),
                section=self._section(
                    metadata
                ),

                # Citation metadata - bắt buộc
                # cho citation validator
                title=document.title,
                document_number=(
                    document.document_number
                ),

                content_hash=(
                    chunk.content_hash
                ),

                embedding_model=(
                    runtime.embeddings
                    .model_name
                ),
                embedding_version=(
                    runtime.embeddings
                    .model_version
                ),

                sparse_model=(
                    runtime.sparse_provider
                    .model_name
                ),
                sparse_version=(
                    runtime.sparse_provider
                    .model_version
                ),

                index_version=(
                    runtime.settings
                    .qdrant_collection
                ),
            )

            points.append(
                QdrantPointInput(
                    payload=payload,
                    dense_vector=(
                        dense_vector
                    ),
                    sparse_vector=(
                        sparse_vector
                    ),
                )
            )

        vector_store = (
            runtime.vector_store
        )

        if isinstance(
            vector_store,
            QdrantVectorStore,
        ):
            # Re-digitize cùng version:
            # xóa index version cũ trước,
            # tránh point cũ còn tồn tại.
            await (
                vector_store
                .delete_version_points(
                    str(
                        version.id
                    ),
                    tenant_id=(
                        resolved_tenant_id
                    ),
                )
            )

            await (
                vector_store
                .upsert_chunks(
                    points
                )
            )

            return

        if isinstance(
            vector_store,
            InMemoryVectorStore,
        ):
            records: list[
                VectorRecord
            ] = []

            for point in points:
                payload = (
                    point.payload
                    .model_dump(
                        mode="json"
                    )
                )

                # InMemoryVectorStore
                # hiện đọc sparse vector
                # từ payload.
                payload[
                    "sparse_vector"
                ] = (
                    point.sparse_vector
                    .model_dump(
                        mode="json"
                    )
                )

                records.append(
                    VectorRecord(
                        id=(
                            point
                            .payload
                            .chunk_id
                        ),
                        vector=(
                            point
                            .dense_vector
                        ),
                        payload=payload,
                    )
                )

            await (
                vector_store
                .upsert(records)
            )

            return

        raise RuntimeError(
            "Unsupported vector store."
        )

    async def update_document_access(
        self,
        *,
        document_id: UUID,
        access_scope: (
            DocumentAccessScope
        ),
        allowed_units: list[str],
    ) -> None:
        runtime = (
            get_p234_rag_runtime()
        )

        units = self._normalize_units(
            access_scope=access_scope,
            allowed_units=(
                allowed_units
            ),
        )

        classification = (
            self._classification(
                access_scope
            )
        )

        owner_unit = (
            "PUBLIC"
            if (
                access_scope
                == (
                    DocumentAccessScope
                    .PUBLIC
                )
            )
            else units[0]
        )

        # Derive tenant_id for the Qdrant payload filter. The two
        # callers of ``update_document_access`` are:
        #   * PUBLIC scope → tenant_id is a sentinel "public".
        #   * DEPARTMENT scope → first bound department code (lowercase).
        # Falls back to "public" if ``units`` is empty (defensive —
        # should never happen for DEPARTMENT scope which requires ≥1
        # unit, but the handler enforces that already).
        if (
            access_scope
            == DocumentAccessScope.PUBLIC
        ) or not units:
            resolved_tenant_id = "public"
        else:
            resolved_tenant_id = units[0].lower()

        update_payload = {
            "allowed_roles": [],
            "allowed_units": units,
            "classification": (
                classification
            ),
            "owner_unit": (
                owner_unit
            ),
            # tenant_id lives on the same payload write so a single
            # ``set_payload`` covers every field, including for the
            # InMemoryVectorStore branch (no separate step needed).
            # Filtering by tenant_id would break scope transitions
            # (B-P2-08), so we filter by document_id only and let the
            # new tenant_id land via this payload.
            "tenant_id": (
                resolved_tenant_id
            ),
        }

        vector_store = (
            runtime.vector_store
        )

        if isinstance(
            vector_store,
            QdrantVectorStore,
        ):
            if not await (
                vector_store
                .collection_exists()
            ):
                return

            await (
                vector_store.client
                .set_payload(
                    collection_name=(
                        vector_store
                        .collection
                    ),
                    payload=(
                        update_payload
                    ),
                    # Filter by document_id ONLY. We must NOT include
                    # ``tenant_id`` in the filter because the existing
                    # Qdrant points still carry the OLD tenant_id; the
                    # filter would then match zero points and the
                    # payload update would silently no-op (B-P2-08).
                    # The document_id is stable across scope changes,
                    # so it is a safe filter. The new tenant_id is
                    # written into the payload itself via the
                    # bulk_update step below.
                    points=Filter(
                        must=[
                            FieldCondition(
                                key=(
                                    "document_id"
                                ),
                                match=(
                                    MatchValue(
                                        value=str(
                                            document_id
                                        )
                                    )
                                ),
                            ),
                        ]
                    ),
                    wait=True,
                )
            )

            # tenant_id is part of update_payload above, so the
            # ``set_payload`` call also rewrites tenant_id on the
            # matching points. No separate step required.
            return

        if isinstance(
            vector_store,
            InMemoryVectorStore,
        ):
            for record in (
                vector_store
                .records
                .values()
            ):
                if (
                    str(
                        record.payload.get(
                            "document_id"
                        )
                    )
                    != str(
                        document_id
                    )
                ):
                    continue

                record.payload.update(
                    update_payload
                )

            return

        raise RuntimeError(
            "Unsupported vector store."
        )

    async def reindex_section(
        self,
        *,
        section_id: UUID,
    ) -> None:
        section = await (
            self._session.get(
                DocumentSectionModel,
                section_id,
            )
        )

        if section is None:
            return

        document_version = await (
            self._session.get(
                DocumentVersionModel,
                section.version_id,
            )
        )

        if document_version is None:
            return

        document = await (
            self._session.get(
                DocumentModel,
                document_version.document_id,
            )
        )

        if document is None:
            return

        # Derive tenant_id from the document's bound departments. We
        # previously hardcoded ``settings.school_code`` here, which
        # silently turned every chunk into a tenant_id="hust" point
        # regardless of which school actually owned the document.
        # Now we resolve it the same way ``index_chunks`` does: take
        # the first allowed unit from the document_departments join.
        dept_result = await self._session.execute(
            select(DepartmentModel.code)
            .join(
                DocumentDepartmentModel,
                DocumentDepartmentModel.department_id
                == DepartmentModel.id,
            )
            .where(
                DocumentDepartmentModel.document_id
                == document.id
            )
            .order_by(DepartmentModel.code)
            .limit(1)
        )
        first_dept_code = dept_result.scalar_one_or_none()
        if first_dept_code is not None:
            resolved_tenant_id = first_dept_code.lower()
        elif (
            document.access_scope
            == (
                DocumentAccessScope
                .PUBLIC
            )
        ):
            resolved_tenant_id = "public"
        else:
            # Department-bound document but no departments attached —
            # skip the reindex, the doc was misconfigured upstream.
            return

        base_chunk_result = await (
            self._session.execute(
                select(
                    DocumentChunkModel
                )
                .where(
                    DocumentChunkModel
                    .section_id
                    == section.id
                )
                .order_by(
                    DocumentChunkModel
                    .chunk_index
                )
                .limit(1)
            )
        )

        base_chunk = (
            base_chunk_result
            .scalar_one_or_none()
        )

        if base_chunk is None:
            return

        version_result = await (
            self._session.execute(
                select(
                    DocumentSectionVersionModel
                )
                .where(
                    DocumentSectionVersionModel
                    .section_id
                    == section.id
                )
                .order_by(
                    DocumentSectionVersionModel
                    .version_number
                )
            )
        )

        section_versions = list(
            version_result
            .scalars()
            .all()
        )

        if not section_versions:
            return

        access_scope = (
            DocumentAccessScope(
                document.access_scope
            )
        )

        if (
            access_scope
            == DocumentAccessScope.PUBLIC
        ):
            allowed_units = ["*"]

        else:
            department_result = await (
                self._session.execute(
                    select(
                        DepartmentModel.code
                    )
                    .join(
                        DocumentDepartmentModel,
                        (
                            DocumentDepartmentModel
                            .department_id
                            == DepartmentModel.id
                        ),
                    )
                    .where(
                        DocumentDepartmentModel
                        .document_id
                        == document.id,

                        DepartmentModel
                        .is_active
                        .is_(True),
                    )
                )      
            )

            allowed_units = [
                str(code)
                .strip()
                .upper()
                for code
                in (
                    department_result
                    .scalars()
                    .all()
                )
                if str(code).strip()
            ]

            allowed_units = list(
                dict.fromkeys(
                    allowed_units
                )
            )

            if not allowed_units:
                raise ValueError(
                    "Department-restricted "
                    "document requires at "
                    "least one allowed unit."
                )

        classification = (
            self._classification(
                access_scope
            )
        )

        owner_unit = (
            "PUBLIC"
            if (
                access_scope
                == DocumentAccessScope.PUBLIC
            )
            else allowed_units[0]
        )

        runtime = (
            get_p234_rag_runtime()
        )

        heading_path = list(
            section.heading_path
            or []
        )

        heading = " > ".join(
            str(item)
            for item in heading_path
            if str(item).strip()
        )

        prefix_parts = [
            document.title,
            document.document_number,
            heading,
        ]

        prefix = " | ".join(
            str(item).strip()
            for item in prefix_parts
            if item
            and str(item).strip()
        )

        embedding_texts: list[
            str
        ] = []

        content_hashes: list[
            str
        ] = []

        point_metadata: list[
            tuple[
                DocumentSectionVersionModel,
                str,
                str,
            ]
        ] = []

        for section_version in (
            section_versions
        ):  
            content = (
                section_version
                .content
                .strip()
            )

            if not content:
                continue

            embedding_text = (
                f"{prefix}\n{content}"
                .strip()
            )

            content_hash = (
                hashlib.sha256(
                    content.encode(
                        "utf-8"
                    )
                )
                .hexdigest()
            )

            embedding_texts.append(
                embedding_text
            )

            content_hashes.append(
                content_hash
            )

            point_metadata.append(
                (
                    section_version,
                    embedding_text,
                    content_hash,
                )
            )

        if not point_metadata:
            return

        dense_vectors = await (
            runtime.embeddings
            .embed_documents(
                embedding_texts,
                content_hashes=(
                    content_hashes
                ),
            )
        )

        sparse_vectors = (
            runtime.sparse_provider
            .sparse_embed_documents(
                embedding_texts
            )
        )

        if (
            len(dense_vectors)
            != len(point_metadata)
            or len(sparse_vectors)
            != len(point_metadata)
        ):
            raise RuntimeError(
                "Embedding result count "
                "does not match section "
                "version count."
            )

        base_metadata = dict(
            base_chunk.metadata_json
            or {}
        )

        points: list[
            QdrantPointInput
        ] = []

        for (
            item,
            dense_vector,
            sparse_vector,
        ) in zip(
            point_metadata,
            dense_vectors,
            sparse_vectors,
            strict=True,
        ):
            (
                section_version,
                _embedding_text,
                content_hash,
            ) = item

            valid_from = (
                datetime.combine(
                    section_version
                    .effective_from,
                    time.min,
                    tzinfo=timezone.utc,
                )
            )

            valid_to = None

            if (
                section_version
                .effective_to
                is not None
            ):
                valid_to = (
                    datetime.combine(
                        section_version
                        .effective_to,
                        time.max,
                        tzinfo=timezone.utc,
                    )
                )

            payload = QdrantPayload(
                tenant_id=(
                    resolved_tenant_id
                ),

                document_id=str(
                    document.id
                ),

                version_id=str(
                    document_version.id
                ),

                chunk_id=(
                    build_section_version_point_id(
                        section_version.id
                    )
                ),

                owner_unit=(
                    owner_unit
                ),

                allowed_roles=[],

                allowed_units=(
                    allowed_units
                ),

                classification=(
                    classification
                ),

                status="published",

                valid_from=(
                    valid_from
                ),

                valid_to=(
                    valid_to
                ),

                page=(
                    section.page
                    or self._page(
                        base_metadata
                    )
                ),

                section=(
                    section.heading
                    or self._section(
                        base_metadata
                    )
                ),

                # Citation metadata - bắt buộc
                # cho citation validator
                title=document.title,
                document_number=(
                    document.document_number
                ),

                content_hash=(
                    content_hash
                ),

                embedding_model=(
                    runtime.embeddings
                    .model_name
                ),

                embedding_version=(
                    runtime.embeddings
                    .model_version
                ),

                sparse_model=(
                    runtime
                    .sparse_provider
                    .model_name
                ),

                sparse_version=(
                    runtime
                    .sparse_provider
                    .model_version
                ),

                index_version=(
                    runtime.settings
                    .qdrant_collection
                ),  
            )

            points.append(
                QdrantPointInput(
                    payload=payload,
                    dense_vector=(
                        dense_vector
                    ),
                    sparse_vector=(
                        sparse_vector
                    ),
                )
            )

        await (
            self._upsert_points(
                points
            )
        )