from datetime import (
    date,
)
import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import (
    and_,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.application.common.interfaces.hybrid_retrieval_service import (
    HybridRetrievalActor,
    HybridRetrievalItem,
    HybridRetrievalService,
)
from src.config import Settings
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.domain.enums.document_metadata_draft_status import (
    DocumentMetadataDraftStatus,
)
from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)

from src.infrastructure.ai.rag_runtime import (
    get_p234_rag_runtime,
)
from src.infrastructure.ai.rag_index_service import (
    build_section_version_point_id,
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
from src.persistence.tenant.models.document_section_metadata_draft import (
    DocumentSectionMetadataDraftModel,
)
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)

from src.domain.schemas import (
    ClassificationLevel,
    RetrievedChunk,
    UserContext,
)
from src.retrieval.hybrid import (
    HybridRetriever,
)
from src.retrieval.sparse import (
    SparseRetriever,
)
from src.persistence.tenant.models.document_application_scope import (
    DocumentApplicationScopeModel,
)


class _P234CandidateRepository:
    """
    Adapter in-memory cho thuật toán
    HybridRetriever cũ.

    Không kết nối AI PostgreSQL.
    """

    def __init__(
        self,
        candidates: list[
            dict[str, Any]
        ],
    ) -> None:
        self._candidates = list(
            candidates
        )

        self._contents = {
            str(
                item["chunk_id"]
            ): str(
                item["text"]
            )
            for item
            in candidates
        }

    def list_searchable_chunks(
        self,
        user: UserContext,
        as_of_date: date | None = None,
    ) -> list[dict]:
        # Candidates đã được
        # PostgreSQL BE filter trước.
        del user
        del as_of_date

        return list(
            self._candidates
        )

    def get_chunk_contents(
        self,
        chunk_ids: list[str],
    ) -> dict[str, str]:
        return {
            chunk_id: (
                self._contents[
                    chunk_id
                ]
            )
            for chunk_id
            in chunk_ids
            if chunk_id
            in self._contents
        }

    def create_audit_log(
        self,
        **kwargs,
    ) -> None:
        # Không ghi vào AI DB cũ.
        #
        # P-234 đã có activity log
        # và audit pipeline riêng.
        del kwargs
        return None


class AiHybridRetrievalService(
    HybridRetrievalService
):
    def __init__(
        self,
        settings: Settings,
        session: AsyncSession,
    ) -> None:
        self._settings = settings
        self._session = session

    async def _load_candidates(
        self,
        *,
        department: str,
        as_of_date: date | None,
        is_admin: bool = False,
    ) -> list[
        dict[str, Any]
    ]:
        # NOTE: the previous ORM-based query targeted
        # Phase 5: auto_digitize inserts into public.document_chunks
        # (clean-arch), so the RAG retrieval query reads from the public schema.
        #
        # Tables used:
        #   public.documents(id, access_scope, title, legal_status, effective_date)
        #   public.document_versions(id, processing_status, legal_status)
        #   public.document_chunks(id, version_id, text, embedding_text, metadata_json)
        #   public.document_departments(document_id, department_id)   -- ACL join table
        #   public.departments(id, code)                            -- department codes
        #
        # Access: PUBLIC docs always readable. DEPARTMENT docs readable only
        # when user's department code appears in the document_departments join,
        # or when user has admin role (cross-school access).
        from sqlalchemy import text as _sql_text

        department_code = (
            department
            .strip()
            .upper()
            or "PUBLIC"
        )
        target_date = as_of_date or date.today()

        sql = _sql_text(
            """
            SELECT DISTINCT ON (c.id)
                c.id::text              AS chunk_id,
                c.text                 AS text,
                c.embedding_text       AS embedding_text,
                c.metadata_json        AS metadata_json,
                c.version_id::text     AS version_id,
                d.id::text             AS document_id,
                d.document_number      AS document_number,
                d.title                AS title,
                d.access_scope         AS access_scope,
                COALESCE(
                    ARRAY_AGG(dep.code) FILTER (WHERE dep.code IS NOT NULL) OVER (PARTITION BY c.id),
                    ARRAY[]::text[]
                )                       AS allowed_departments,
                d.legal_status         AS legal_status,
                d.effective_date       AS effective_date,
                v.processing_status    AS processing_status
            FROM public.document_chunks     AS c
            JOIN public.document_versions   AS v ON v.id = c.version_id
            JOIN public.documents           AS d ON d.id = v.document_id
            LEFT JOIN public.document_departments AS dd ON dd.document_id = d.id
            LEFT JOIN public.departments         AS dep ON dep.id = dd.department_id
            -- 2026-09-06 metadata cleanup: only RAG-curated statuses
            -- (``approved`` / ``indexed`` / ``published``) flow into
            -- retrieval. Pre-curation states (``parsed``, ``pending_review``,
            -- ``review_required``, ``received``, ``queued``, ``failed``,
            -- ``rejected``) are silently dropped so docs with incomplete
            -- metadata do not pollute the search index. ``parsed`` is
            -- excluded because it represents the transient OCR-in-progress
            -- state which can carry partial / unvalidated chunks.
            WHERE v.processing_status IN ('approved', 'indexed', 'published')
              AND d.legal_status     IN ('effective', 'draft', 'scheduled', 'superseded', 'expired')
              AND (d.effective_date IS NULL OR d.effective_date <= :target_date)
              AND (
                    :is_admin = TRUE
                 OR d.access_scope = 'PUBLIC'
                 OR (
                    d.access_scope = 'DEPARTMENT'
                    AND dep.code = :department_code
                 )
              )
              -- Low-confidence flag: chunks the OCR engine flagged as
              -- unreliable (average page confidence below threshold) are
              -- dropped from RAG.  The flag is stored in the chunk
              -- metadata_json column by the parser; reading it via
              -- ``->>`` keeps the JSON query plan index-friendly.
              -- Default ``false`` when the field is missing so legacy
              -- chunks (no flag) still surface.
              AND COALESCE(
                    (c.metadata_json->>'low_confidence')::boolean,
                    FALSE
                  ) = FALSE
            ORDER BY c.id
            """
        )
        rows = (
            await self._session.execute(
                sql,
                {
                    "target_date": target_date,
                    "department_code": department_code,
                    "is_admin": is_admin,
                },
            )
        ).mappings().all()

        results: list[dict[str, Any]] = []
        for row in rows:
            metadata = dict(row.get("metadata_json") or {})
            access_scope = row.get("access_scope")
            allowed_departments = list(
                row.get("allowed_departments") or []
            )
            # CRITICAL: for DEPARTMENT-scope documents, the actual allowed_units
            # must reflect the departments in document_departments join (NOT
            # the wildcard "*"). Otherwise downstream access checks
            # (can_access_document, build_access_filter) will incorrectly
            # treat DEPARTMENT docs as PUBLIC and leak them across schools.
            # See BUGS_FOUND.md cross-school leak analysis.
            if access_scope == "DEPARTMENT" and allowed_departments:
                # Use the actual departments this document is bound to.
                units = list(allowed_departments)
            else:
                # PUBLIC docs (or DEPARTMENT docs with no department join,
                # which should not happen but is defensive) are accessible
                # to any user.
                units = ["*"]
            metadata.update(
                {
                    "chunk_id": row["chunk_id"],
                    "version_id": row["version_id"],
                    "document_id": row["document_id"],
                    "document_number": row["document_number"],
                    "title": row["title"],
                    "access_scope": access_scope,
                    "allowed_departments": allowed_departments,
                    "legal_status": row.get("legal_status"),
                    "effective_date": (
                        row["effective_date"].isoformat()
                        if row.get("effective_date")
                        else None
                    ),
                    "tenant_id": (
                        row["access_scope"].lower()
                        if row.get("access_scope") == "PUBLIC"
                        else department_code.lower()
                    ),
                    # Required by can_access_document / QdrantPayload validation
                    # These fields come from Qdrant index, not PostgreSQL.
                    # Using placeholder values since access check only needs
                    # status, tenant_id, classification, allowed_units, valid_from.
                    "status": "published",
                    "classification": (
                        "public"
                        if row.get("access_scope") == "PUBLIC"
                        else "internal"
                    ),
                    "allowed_units": units,
                    "allowed_roles": [],
                    "valid_from": (
                        row["effective_date"].isoformat()
                        if row.get("effective_date")
                        else "2026-01-01T00:00:00Z"
                    ),
                    "valid_to": None,
                    "content_hash": hashlib.sha256(str(row["text"]).encode("utf-8")).hexdigest(),
                    "embedding_model": "postgresql-derivation",
                    "embedding_version": "1",
                    "index_version": "postgresql-derivation",
                }
            )
            results.append(
                {
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "embedding_text": row.get("embedding_text") or row["text"],
                    "payload": metadata,
                }
            )
        return results

        department_match = exists(
            select(
                DocumentDepartmentModel
                .document_id
            )
            .join(
                DepartmentModel,
                DepartmentModel.id
                == (
                    DocumentDepartmentModel
                    .department_id
                ),
            )
            .where(
                DocumentDepartmentModel
                .document_id
                == DocumentModel.id,

                DepartmentModel
                .is_active
                .is_(True),

                func.upper(
                    DepartmentModel.code
                )
                == department_code,
            )
        )

        latest_source_version = (
            select(
                DocumentVersionModel
                .document_id
                .label(
                    "document_id"
                ),

                func.max(
                    DocumentVersionModel
                    .version_number
                ).label(
                    "version_number"
                ),
            )
            .group_by(
                DocumentVersionModel
                .document_id
            )
            .subquery()
        )

        statement = (
            select(
                DocumentChunkModel,
                DocumentVersionModel,
                DocumentModel,
                DocumentSectionModel,
            )
            .join(
                DocumentVersionModel,
                DocumentVersionModel.id
                == (
                    DocumentChunkModel
                    .version_id
                ),
            )
            .join(
                latest_source_version,
                and_(
                    (
                        latest_source_version
                        .c.document_id
                        == DocumentVersionModel
                        .document_id
                    ),
                    (
                        latest_source_version
                        .c.version_number
                        == DocumentVersionModel
                        .version_number
                    ),
                ),
            )
            .join(
                DocumentModel,
                DocumentModel.id
                == (
                    DocumentVersionModel
                    .document_id
                ),
            )
            .outerjoin(
                DocumentSectionModel,
                DocumentSectionModel.id
                == (
                    DocumentChunkModel
                    .section_id
                ),
            )
            .join(
                DocumentSectionMetadataDraftModel,
                (
                    DocumentSectionMetadataDraftModel
                    .chunk_id
                    == DocumentChunkModel.id
                ),
            )
            .where(
                # A-01 đã digitize xong.
                DocumentVersionModel
                .processing_status
                == (
                    DocumentProcessingStatus
                    .DA_SO_HOA
                    .value
                ),

                # A-03:
                # metadata phải approved
                # mới được retrieval.
                DocumentSectionMetadataDraftModel
                .status
                == (
                    DocumentMetadataDraftStatus
                    .APPROVED
                    .value
                ),

                # Chỉ văn bản đang hiệu lực.
                DocumentModel
                .legal_status
                == (
                    DocumentLegalStatus
                    .DANG_HIEU_LUC
                    .value
                ),

                DocumentModel
                .effective_date
                <= target_date,

                # Authorization ở DB:
                # PUBLIC hoặc đúng phòng.
                or_(
                    DocumentModel
                    .access_scope
                    == (
                        DocumentAccessScope
                        .PUBLIC
                        .value
                    ),

                    and_(
                        DocumentModel
                        .access_scope
                        == (
                            DocumentAccessScope
                            .DEPARTMENT
                            .value
                        ),
                        department_match,
                    ),
                ),
            )
            .order_by(
                DocumentModel.id,
                DocumentChunkModel
                .chunk_index,
            )
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        rows = result.all()

        if not rows:
            return []

        section_ids: set[
            UUID
        ] = {
            section.id
            for (
                _chunk,
                _version,
                _document,
                section,
            )
            in rows
            if section is not None
        }

        versioned_section_ids: set[
            UUID
        ] = set()

        if section_ids:
            versioned_section_result = await (
                self._session.execute(
                    select(
                        DocumentSectionVersionModel
                        .section_id
                    )
                    .where(
                        DocumentSectionVersionModel
                        .section_id
                        .in_(
                            section_ids
                        )
                    )
                    .distinct()
                )
            )

            versioned_section_ids = {
                section_id
                for section_id
                in (
                    versioned_section_result
                    .scalars()
                    .all()
                )
            }

        effective_versions: dict[
            UUID,
            DocumentSectionVersionModel,
        ] = {}

        if section_ids:
            version_statement = (
                select(
                    DocumentSectionVersionModel
                )
                .where(
                    DocumentSectionVersionModel
                    .section_id
                    .in_(
                        section_ids
                    ),

                    DocumentSectionVersionModel
                    .effective_from
                    <= target_date,

                    or_(
                        DocumentSectionVersionModel
                        .effective_to
                        .is_(None),

                        DocumentSectionVersionModel
                        .effective_to
                        >= target_date,
                    ),
                )
            )

            # Khi user không chủ động
            # query lịch sử, A-04 current
            # là điều kiện bổ sung.
            if as_of_date is None:
                version_statement = (
                    version_statement
                    .where(
                        DocumentSectionVersionModel
                        .is_current
                        .is_(True)
                    )
                )

            version_result = await (
                self._session.execute(
                    version_statement
                )
            )

            for section_version in (
                version_result
                .scalars()
                .all()
            ):
                effective_versions[
                    section_version.section_id
                ] = section_version

        document_ids: set[
            UUID
        ] = {
            document.id
            for (
                _chunk,
                _version,
                document,
                _section,
            )
            in rows
        }

        department_result = await (
            self._session.execute(
                select(
                    DocumentDepartmentModel
                    .document_id,
                    DepartmentModel.code,
                )
                .join(
                    DepartmentModel,
                    DepartmentModel.id
                    == (
                        DocumentDepartmentModel
                        .department_id
                    ),
                )
                .where(
                    DocumentDepartmentModel
                    .document_id
                    .in_(
                        document_ids
                    ),

                    DepartmentModel
                    .is_active
                    .is_(True),
                )
            )
        )

        units_by_document: dict[
            UUID,
            list[str],
        ] = {}

        for (
            document_id,
            code,
        ) in department_result.all():
            normalized_code = (
                str(code)
                .strip()
                .upper()
            )

            if not normalized_code:
                continue

            units_by_document.setdefault(
                document_id,
                [],
            ).append(
                normalized_code
            )

        candidates: list[
            dict[str, Any]
        ] = []

        versioned_sections_added: set[
            UUID
        ] = set()

        for (
            chunk,
            version,
            document,
            section,
        ) in rows:
            if (
                document.access_scope
                == (
                    DocumentAccessScope
                    .PUBLIC
                    .value
                )
            ):
                allowed_units = ["*"]

            else:
                allowed_units = list(
                    dict.fromkeys(
                        units_by_document
                        .get(
                            document.id,
                            [],
                        )
                    )
                )

                # Fail closed.
                if not allowed_units:
                    continue

            metadata = dict(
                chunk.metadata_json
                or {}
            )

            section_version = None

            if section is not None:
                section_version = (
                    effective_versions.get(
                        section.id
                    )
                )

            #
            # Nếu A-04 có version phù hợp:
            #
            # - dùng đúng content của version đó
            # - chỉ tạo 1 retrieval unit cho section
            # - ID phải trùng point được
            #   RagIndexService index.
            #
            if section_version is not None:
                if (
                    section.id
                    in versioned_sections_added
                ):
                    continue

                versioned_sections_added.add(
                    section.id
                )

                chunk_id = (
                    build_section_version_point_id(
                        section_version.id
                    )
                )

                candidate_text = (
                    section_version
                    .content
                    .strip()
                )

                if not candidate_text:
                    continue

                heading = ""

                if (
                    section.heading_path
                ):
                    heading = " > ".join(
                        str(item)
                        for item
                        in section.heading_path
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

                embedding_text = (
                    f"{prefix}\n"
                    f"{candidate_text}"
                ).strip()

                metadata[
                    "section_version_id"
                ] = str(
                    section_version.id
                )

                metadata[
                    "section_version_number"
                ] = (
                    section_version
                    .version_number
                )

                metadata[
                    "section_version_is_current"
                ] = (
                    section_version
                    .is_current
                )

                metadata[
                    "section_effective_from"
                ] = (
                    section_version
                    .effective_from
                    .isoformat()
                )

                metadata[
                    "section_effective_to"
                ] = (
                    section_version
                    .effective_to
                    .isoformat()
                    if (
                        section_version
                        .effective_to
                        is not None
                    )
                    else None
                )

                # Giữ trace về chunk gốc
                # mà metadata đã được approve.
                metadata[
                    "source_chunk_id"
                ] = str(
                    chunk.id
                )

            elif (
                section is not None
                and section.id
                in versioned_section_ids
            ):
                # Section đã được quản lý bằng
                # A-04 nhưng tại target_date
                # không có version hiệu lực.
                #
                # Không được fallback về raw
                # chunk vì có thể làm sống lại
                # nội dung đã hết hiệu lực.
                continue

            else:
                chunk_id = str(
                    chunk.id
                )

                candidate_text = (
                    chunk.text
                )

                embedding_text = (
                    chunk.embedding_text
                )

            metadata.update(
                {
                    "tenant_id": (
                        allowed_units[0].lower()
                        if (
                            allowed_units
                            and allowed_units != ["*"]
                        )
                        else "public"
                    ),

                    "document_id": str(
                        document.id
                    ),

                    "version_id": str(
                        version.id
                    ),

                    "document_number": (
                        document
                        .document_number
                    ),

                    "title": (
                        document.title
                    ),

                    "issued_by": (
                        document.issued_by
                    ),

                    "legal_status": (
                        document
                        .legal_status
                    ),

                    "access_scope": (
                        document
                        .access_scope
                    ),

                    "allowed_units": (
                        allowed_units
                    ),

                    "effective_from": (
                        document
                        .effective_date
                        .isoformat()
                    ),

                    "source_filename": (
                        version
                        .source_filename
                    ),

                    "page": (
                        section.page
                        if section
                        is not None
                        else metadata.get(
                            "page"
                        )
                    ),

                    "section": (
                        section.heading
                        if (
                            section
                            is not None
                            and section.heading
                        )
                        else metadata.get(
                            "section"
                        )
                    ),
                }
            )

            if section is not None:
                metadata[
                    "section_type"
                ] = (
                    section.section_type
                )

                metadata[
                    "section_number"
                ] = (
                    section.section_number
                )

                metadata[
                    "heading_path"
                ] = list(
                    section.heading_path
                    or []
                )

            candidates.append(
                {
                    "chunk_id": (
                        chunk_id
                    ),

                    "text": (
                        candidate_text
                    ),

                    "embedding_text": (
                        embedding_text
                    ),

                    "payload": (
                        metadata
                    ),
                }
            )

        return candidates

    def _build_user_context(
        self,
        actor: HybridRetrievalActor,
    ) -> UserContext:
        return UserContext(
            user_id=str(
                actor.user_id
            ),
            tenant_id=(
                actor.department
                .strip()
                .lower()
                or "public"
            ),
            department=(
                actor.department
                .strip()
                .upper()
                or "PUBLIC"
            ),
            roles={
                role.strip().lower()
                for role in actor.roles
                if role.strip()
            }
            or {"staff"},
            clearance_level=(
                ClassificationLevel(
                    self._settings
                    .rag_default_clearance
                )
            ),
        )


    def _build_retriever(
        self,
        *,
        candidates: list[
            dict[str, Any]
        ],
        runtime,
    ) -> HybridRetriever:
        repository = (
            _P234CandidateRepository(
                candidates
            )
        )

        sparse_retriever = (
            SparseRetriever(
                embedding_provider=(
                    runtime
                    .sparse_provider
                ),
                vector_store=(
                    runtime
                    .vector_store
                ),
                content_provider=(
                    repository
                ),  
            )
        )

        return HybridRetriever(
            runtime.settings,
            repository,
            runtime.embeddings,
            runtime.vector_store,
            sparse_retriever,
        )


    async def _run_retrieval(
        self,
        *,
        query: str,
        candidates: list[
            dict[str, Any]
        ],
        runtime,
        user_context: UserContext,
        as_of_date: date | None,
        embed_text: str | None = None,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        retriever = (
            self._build_retriever(
                candidates=candidates,
                runtime=runtime,
            )
        )

        return await retriever.search(
            query=query,
            user=user_context,
            as_of_date=as_of_date,
            embed_text=embed_text,
        )


    @staticmethod
    def _normalize_document_number(
        value,
    ) -> str:
        if value is None:
            return ""

        return (
            str(value)
            .strip()
            .casefold()
        )


    async def _expand_cross_references(
        self,
        *,
        query: str,
        results: list[
            RetrievedChunk
        ],
        candidates: list[
            dict[str, Any]
        ],
        runtime,
        user_context: UserContext,
        as_of_date: date | None,
    ) -> list[RetrievedChunk]:
        if not results:
            return []

        expanded = list(
            results
        )

        seen_chunk_ids = {
            item.chunk_id
            for item in results
        }

        candidates_by_number: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        candidates_by_document_id: dict[
            str,
            list[dict[str, Any]],
        ] = {}

        for candidate in candidates:
            payload = dict(
                candidate.get(
                    "payload"
                )   
                or {}
            )

            document_number = (
                self
                ._normalize_document_number(
                    payload.get(
                        "document_number"
                    )
                )
            )

            if document_number:
                candidates_by_number.setdefault(
                    document_number,
                    [],
                ).append(
                    candidate
                )

            document_id = str(
                payload.get(
                    "document_id"
                )
                or ""
            ).strip()

            if document_id:
                candidates_by_document_id.setdefault(
                    document_id,
                    [],
                ).append(
                    candidate
                )

        async def add_best_related(
            *,
            parent: RetrievedChunk,
            related_candidates: list[
                dict[str, Any]
            ],
            related_query: str,
            extra_metadata: dict,
        ) -> None:
            related_results = await (
                self._run_retrieval(
                    query=related_query,
                    candidates=(
                        related_candidates
                    ),
                    runtime=runtime,
                    user_context=(
                        user_context
                    ),
                    as_of_date=(
                        as_of_date
                    ),
                )
            )

            for related in (
                related_results
            ):
                if (
                    related.chunk_id
                    in seen_chunk_ids
                ):
                    continue

                metadata = dict(
                    related.metadata
                    or {}
                )

                metadata.update(
                    extra_metadata
                )

                expanded.append(
                    RetrievedChunk(
                        chunk_id=(
                            related.chunk_id
                        ),
                        text=related.text,
                        score=(
                            related.score
                        ),
                        source=(
                            f"{related.source}"
                            "+cross_reference"
                        ),
                        metadata=metadata,
                    )
                )

                seen_chunk_ids.add(
                    related.chunk_id
                )

                # Mỗi reference chỉ cần
                # lấy kết quả liên quan nhất.
                break

        #
        # 1. Cross-reference được AI
        #    extract và A-03 approve.
        #
        for parent in list(
            results
        ):
            references = (
                parent.metadata.get(
                    "cross_references"
                )
                or []
            )

            if not isinstance(
                references,
                list,
            ):
                continue

            for reference in references:
                if not isinstance(
                    reference,
                    dict,
                ):
                    continue

                document_number = (
                    self
                    ._normalize_document_number(
                        reference.get(
                            "document_number"
                        )
                    )
                )

                if not document_number:
                    continue

                related_candidates = (
                    candidates_by_number
                    .get(
                        document_number,
                        [],
                    )
                )

                if not related_candidates:
                    continue

                context_text = str(
                    reference.get(
                        "context_text"
                    )
                    or ""
                ).strip()

                related_query = (
                    context_text
                    or query
                )

                await add_best_related(
                    parent=parent,
                    related_candidates=(
                        related_candidates
                    ),
                    related_query=(
                        related_query
                    ),
                    extra_metadata={
                        "cross_reference_of": (
                            parent.chunk_id
                        ),
                        "cross_reference_type": (
                            "metadata"
                        ),
                        "cross_reference_"
                        "document_number": (
                            reference.get(
                                "document_number"
                            )
                        ),
                        "cross_reference_"
                        "context": (
                            context_text
                            or None
                        ),
                    },
                )

        #
        # 2. A0-05:
        #    application scope gắn với
        #    source document/version.
        #
        parent_keys: dict[
            tuple[UUID, UUID],
            RetrievedChunk,
        ] = {}

        for parent in results:
            try:
                document_id = UUID(
                    str(
                        parent.metadata[
                            "document_id"
                        ]
                    )
                )

                version_id = UUID(
                    str(
                        parent.metadata[
                            "version_id"
                        ]
                    )
                )   

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            parent_keys[
                (
                    document_id,
                    version_id,
                )
            ] = parent

        if parent_keys:
            source_document_ids = {
                item[0]
                for item
                in parent_keys
            }

            scope_result = await (
                self._session.execute(
                    select(
                        DocumentApplicationScopeModel
                    )
                    .where(
                        DocumentApplicationScopeModel
                        .source_document_id
                        .in_(
                            source_document_ids
                        )
                    )
                )
            )

            scopes = list(
                scope_result
                .scalars()
                .all()
            )

            for scope in scopes:
                parent = parent_keys.get(
                    (
                        scope
                        .source_document_id,

                        scope
                        .source_version_id,
                    )
                )

                if parent is None:
                    continue

                related_candidates = (
                    candidates_by_document_id
                    .get(
                        str(
                            scope
                            .related_document_id
                        ),
                        [],
                    )
                )

                if not related_candidates:
                    # Related document không
                    # nằm trong candidate pool
                    # nghĩa là:
                    #
                    # - không effective
                    # - metadata chưa approve
                    # - hoặc user không có quyền
                    #
                    # => fail closed.
                    continue

                scope_detail = str(
                    scope.scope_detail
                    or ""
                ).strip()

                await add_best_related(
                    parent=parent,
                    related_candidates=(
                        related_candidates
                    ),
                    related_query=(
                        scope_detail
                        or query
                    ),
                    extra_metadata={
                        "cross_reference_of": (
                            parent.chunk_id
                        ),
                        "cross_reference_type": (
                            "application_scope"
                        ),
                        "application_scope_id": (
                            str(
                                scope.id
                            )
                        ),
                        "scope_type": (
                            scope.scope_type
                        ),
                        "scope_detail": (
                            scope.scope_detail
                        ),
                        "reference_nature": (
                            scope
                            .reference_nature
                        ),
                    },
                )

        return expanded

    async def search(
        self,
        *,
        query: str,
        actor: HybridRetrievalActor,
        as_of_date: date | None,
        embed_text: str | None = None,
    ) -> list[
        HybridRetrievalItem
    ]:  
        role_codes = {
            r.strip().lower()
            for r in (actor.roles or set())
        }
        is_admin = bool(
            {"admin", "administrator"}
            & role_codes
        )
        candidates = await (
            self._load_candidates(
                department=(
                    actor.department
                ),
                as_of_date=(
                    as_of_date
                ),
                is_admin=is_admin,
            )
        )

        if not candidates:
            return []

        runtime = (
            get_p234_rag_runtime()
        )

        user_context = (
            self._build_user_context(
                actor
            )
        )

        results = await (
            self._run_retrieval(
                query=query,
                candidates=candidates,
                runtime=runtime,
                user_context=(
                    user_context
                ),
                as_of_date=(
                    as_of_date
                ),
                embed_text=(
                    embed_text
                ),
            )
        )

        results = await (
            self._expand_cross_references(
                query=query,
                results=results,
                candidates=candidates,
                runtime=runtime,
                user_context=(
                    user_context
                ),
                as_of_date=(
                    as_of_date
                ),
            )
        )

        return [
            HybridRetrievalItem(
                chunk_id=(
                    item.chunk_id
                ),
                text=item.text,
                score=item.score,
                source=item.source,
                metadata=dict(
                    item.metadata
                    or {}
                ),
            )
            for item in results
        ]