from __future__ import annotations

import warnings
from datetime import UTC, date, datetime

from sqlalchemy import Select, func, select

from src.db.models import (
    AccessPolicy,
    ApprovalRecord,
    AuditLog,
    Chunk,
    Document,
    DocumentRelation,
    DocumentVersion,
    IngestionJob,
    Section,
    UserFeedback,
)
from src.domain.schemas import ChunkData, DocumentMetadata, LegalStatus, ProcessingStatus, UserContext

# ``src.db.repository.Repository`` is the legacy data-access class.
# Production traffic flows through
# ``src/persistence/tenant/repositories/`` and the admin router
# (see ``src/presentation/api/routers/admin_router.py``) which enforces
# the strict ``INDEXED -> PUBLISHED`` gate. The legacy
# ``Repository.publish_version`` accepts ``APPROVED`` *or* ``INDEXED``,
# which can leave the DB in the inconsistent "PUBLISHED but not in
# Qdrant" state. See BUGS_FOUND.md B-P3-01.
warnings.warn(
    "src.db.repository.Repository is deprecated as of 2026-08-31; "
    "production HTTP traffic already routes through "
    "src.persistence.tenant.repositories.*. "
    "The legacy publish_version gate is WEAKER than the production gate "
    "and may publish a version that is not in Qdrant. "
    "Migrate remaining consumers and delete this module.",
    DeprecationWarning,
    stacklevel=2,
)
from src.ingestion.document_number import DocumentNumberProbe
from src.security.metadata_contract import derive_security_acl
from src.security.policy import can_access_document


class Repository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def find_version_by_checksum(self, checksum: str) -> DocumentVersion | None:
        with self.session_factory() as session:
            return session.scalar(select(DocumentVersion).where(DocumentVersion.checksum == checksum))

    def create_document_version(
        self,
        metadata: DocumentMetadata,
        *,
        checksum: str,
        source_filename: str,
        source_path: str,
        processing_status: ProcessingStatus = ProcessingStatus.RECEIVED,
    ) -> tuple[Document, DocumentVersion]:
        with self.session_factory() as session:
            document = session.scalar(select(Document).where(Document.document_number == metadata.document_number))
            if document is None:
                document = Document(
                    title=metadata.title,
                    document_number=metadata.document_number,
                    issued_by=metadata.issued_by,
                    owner_department=metadata.owner_department.upper(),
                    access_level=metadata.access_level.value,
                    allowed_departments=[item.upper() for item in metadata.allowed_departments],
                    source_url=metadata.source_url,
                )
                session.add(document)
                session.flush()
            else:
                document.title = metadata.title
                document.issued_by = metadata.issued_by
                document.owner_department = metadata.owner_department.upper()
                document.access_level = metadata.access_level.value
                document.allowed_departments = [item.upper() for item in metadata.allowed_departments]
                document.source_url = metadata.source_url

            duplicate_version = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_number == metadata.version_number,
                )
            )
            if duplicate_version:
                raise ValueError(f"Văn bản {metadata.document_number} đã có phiên bản {metadata.version_number}.")

            version = DocumentVersion(
                document_id=document.id,
                version_number=metadata.version_number,
                issued_date=metadata.issued_date,
                effective_from=metadata.effective_from,
                effective_to=metadata.effective_to,
                legal_status=LegalStatus.DRAFT.value,
                processing_status=processing_status.value,
                checksum=checksum,
                source_filename=source_filename,
                source_path=source_path,
                replaces_version_id=metadata.replaces_version_id,
                metadata_json=metadata.model_dump(mode="json"),
            )
            session.add(version)
            session.commit()
            session.refresh(document)
            session.refresh(version)
            return document, version

    def save_sections_and_chunks(
        self,
        *,
        version_id: str,
        sections: list[dict],
        chunks: list[ChunkData],
        warnings: list[str],
    ) -> None:
        with self.session_factory() as session:
            section_ids: list[str] = []
            for index, item in enumerate(sections):
                section = Section(
                    version_id=version_id,
                    section_type=item.get("section_type"),
                    section_number=item.get("section_number"),
                    heading=item.get("heading"),
                    heading_path=item.get("heading_path") or [],
                    content=item.get("text", ""),
                    sort_order=index,
                )
                session.add(section)
                session.flush()
                section_ids.append(section.id)

            for item in chunks:
                section_id = item.section_id
                source_index = item.metadata.get("source_section_index")
                if section_id is None and isinstance(source_index, int) and 0 <= source_index < len(section_ids):
                    section_id = section_ids[source_index]
                session.add(
                    Chunk(
                        id=item.id,
                        version_id=version_id,
                        section_id=section_id,
                        chunk_index=item.chunk_index,
                        text=item.text,
                        embedding_text=item.embedding_text,
                        metadata_json=item.metadata,
                    )
                )

            version = session.get(DocumentVersion, version_id)
            if version is None:
                raise ValueError("Không tìm thấy phiên bản văn bản.")
            version.processing_status = ProcessingStatus.REVIEW_REQUIRED.value
            version.metadata_json = {**version.metadata_json, "warnings": warnings}
            session.commit()

    def get_version(self, version_id: str) -> DocumentVersion | None:
        with self.session_factory() as session:
            return session.get(DocumentVersion, version_id)

    def update_version_source(
        self,
        version_id: str,
        *,
        source_path: str | None = None,
        processing_status: ProcessingStatus | None = None,
        error: str | None = None,
    ) -> None:
        with self.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                return
            if source_path:
                version.source_path = source_path
            if processing_status:
                version.processing_status = processing_status.value
            if error:
                version.metadata_json = {
                    **version.metadata_json,
                    "processing_error": error,
                }
            session.commit()

    def record_document_number_probe(
        self,
        *,
        version_id: str,
        probe: DocumentNumberProbe,
        original_was_auto_detect: bool,
    ) -> None:
        """Persist the document-number probe result on a version row.

        Stores both the resolved value (when available) and the list of
        candidates so data owners can audit the heuristic decision later.
        When the probe cannot make a confident recommendation we still write
        the candidates and flip ``document_number_human_review_required`` so
        the admin UI and approval flow know not to auto-promote the version.
        """
        probe_payload = {
            "document_number_auto_detect": bool(original_was_auto_detect),
            "document_number_candidates": list(probe.candidates),
            "document_number_recommended": probe.recommended,
            "document_number_confidence": float(probe.confidence),
            "document_number_human_review_required": bool(probe.needs_human_review),
            "document_number_matched_pages": {
                candidate: list(pages)
                for candidate, pages in probe.matched_pages.items()
            },
        }
        with self.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                return
            version.metadata_json = {**version.metadata_json, **probe_payload}
            session.commit()

    def get_document(self, document_id: str) -> Document | None:
        with self.session_factory() as session:
            return session.get(Document, document_id)

    def get_chunks_for_version(self, version_id: str) -> list[Chunk]:
        with self.session_factory() as session:
            return list(
                session.scalars(select(Chunk).where(Chunk.version_id == version_id).order_by(Chunk.chunk_index))
            )

    def get_chunk_contents(self, chunk_ids: list[str]) -> dict[str, str]:
        if not chunk_ids:
            return {}
        with self.session_factory() as session:
            rows = session.execute(
                select(Chunk.id, Chunk.text).where(Chunk.id.in_(chunk_ids))
            ).all()
        return {chunk_id: text for chunk_id, text in rows}

    def get_chunk_index_metadata(
        self,
        chunk_ids: list[str],
        *,
        index_version: str,
    ) -> dict[str, dict]:
        """Return PostgreSQL-authoritative fields used to validate Qdrant hits."""

        if not chunk_ids or not index_version.strip():
            return {}
        with self.session_factory() as session:
            rows = session.execute(
                select(Chunk, DocumentVersion, Document)
                .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    Chunk.id.in_(chunk_ids),
                    DocumentVersion.processing_status == ProcessingStatus.PUBLISHED.value,
                    DocumentVersion.legal_status == LegalStatus.EFFECTIVE.value,
                )
            ).all()
        output: dict[str, dict] = {}
        for chunk, version, document in rows:
            try:
                allowed_roles, allowed_units, classification = derive_security_acl(
                    document.access_level,
                    document.allowed_departments,
                    owner_unit=document.owner_department,
                )
            except ValueError:
                continue
            output[chunk.id] = {
                "tenant_id": (version.metadata_json or {}).get("tenant_id"),
                "document_id": document.id,
                "version_id": version.id,
                "chunk_id": chunk.id,
                "status": "published",
                "classification": classification,
                "allowed_roles": allowed_roles,
                "allowed_units": allowed_units,
                "valid_from": (
                    version.effective_from.isoformat()
                    if version.effective_from else None
                ),
                "valid_to": (
                    version.effective_to.isoformat()
                    if version.effective_to else None
                ),
                "content_hash": chunk.content_hash
                or (chunk.metadata_json or {}).get("content_hash"),
                "index_version": index_version,
            }
        return output

    def approve_version(self, version_id: str, approved_by: str) -> DocumentVersion:
        with self.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                raise ValueError("Không tìm thấy phiên bản.")
            if version.processing_status != ProcessingStatus.REVIEW_REQUIRED.value:
                raise ValueError("Phiên bản chưa ở trạng thái chờ duyệt.")
            version.processing_status = ProcessingStatus.APPROVED.value
            version.approved_by = approved_by
            version.approved_at = datetime.now(UTC).replace(tzinfo=None)
            session.commit()
            session.refresh(version)
            return version

    def publish_version(self, version_id: str) -> DocumentVersion:
        with self.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                raise ValueError("Không tìm thấy phiên bản.")
            # Strict gate: a version must have been APPROVED then INDEXED in Qdrant
            # before it can be PUBLISHED. This prevents the PostgreSQL/RAG drift
            # where the database says "published" but the vector store is empty.
            if version.processing_status != ProcessingStatus.INDEXED.value:
                raise ValueError(
                    "Phiên bản phải được duyệt (approved) rồi tạo vector trong Qdrant "
                    "(indexed) trước khi xuất bản. Hiện tại: "
                    f"processing_status={version.processing_status}."
                )

            if version.replaces_version_id:
                replaced = session.get(DocumentVersion, version.replaces_version_id)
                if replaced and replaced.document_id != version.document_id:
                    raise ValueError("Phiên bản bị thay thế phải thuộc cùng một văn bản.")
                if replaced and (version.effective_from is None or version.effective_from <= date.today()):
                    replaced.legal_status = LegalStatus.SUPERSEDED.value

            version.processing_status = ProcessingStatus.PUBLISHED.value
            version.legal_status = (
                LegalStatus.SCHEDULED.value
                if version.effective_from and version.effective_from > date.today()
                else LegalStatus.EFFECTIVE.value
            )
            version.published_at = datetime.now(UTC).replace(tzinfo=None)
            for chunk in version.chunks:
                chunk.metadata_json = {
                    **chunk.metadata_json,
                    "legal_status": LegalStatus.EFFECTIVE.value,
                }
                chunk.indexed_at = datetime.now(UTC).replace(tzinfo=None)
            session.commit()
            session.refresh(version)
            return version

    def refresh_current_legal_statuses(self) -> None:
        """Activate scheduled versions and expire elapsed versions."""
        today = date.today()
        with self.session_factory() as session:
            scheduled = session.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.processing_status == ProcessingStatus.PUBLISHED.value,
                    DocumentVersion.legal_status == LegalStatus.SCHEDULED.value,
                    DocumentVersion.effective_from <= today,
                )
            ).all()
            for version in scheduled:
                version.legal_status = LegalStatus.EFFECTIVE.value
                if version.replaces_version_id:
                    replaced = session.get(DocumentVersion, version.replaces_version_id)
                    if replaced:
                        replaced.legal_status = LegalStatus.SUPERSEDED.value

            expiring = session.scalars(
                select(DocumentVersion).where(
                    DocumentVersion.processing_status == ProcessingStatus.PUBLISHED.value,
                    DocumentVersion.legal_status == LegalStatus.EFFECTIVE.value,
                    DocumentVersion.effective_to.is_not(None),
                    DocumentVersion.effective_to < today,
                )
            ).all()
            for version in expiring:
                version.legal_status = LegalStatus.EXPIRED.value
            session.commit()

    def mark_indexed(self, version_id: str) -> None:
        with self.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version:
                version.processing_status = ProcessingStatus.INDEXED.value
                session.commit()

    def list_searchable_chunks(
        self,
        user: UserContext,
        as_of_date: date | None = None,
    ) -> list[dict]:
        self.refresh_current_legal_statuses()
        target_date = as_of_date or date.today()
        with self.session_factory() as session:
            # Accept both the canonical English enum value ("published") and
            # the legacy / domain-friendly values that the same table can
            # already contain after historical uploads ("Published",
            # "DA_SO_HOA", "CHO_XU_LY_NOI_DUNG"). Without this UNION the
            # hybrid retriever sees zero candidates even though the legacy
            # ``rag_legacy`` schema has plenty of indexed chunks.
            statement: Select = (
                select(Chunk, DocumentVersion, Document)
                .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    DocumentVersion.processing_status.in_(
                        [
                            # Canonical English values (src/domain/schemas.py).
                            ProcessingStatus.PUBLISHED.value,
                            ProcessingStatus.INDEXED.value,
                            # Legacy mixed-case value written by older ingests.
                            "Published",
                        ]
                    )
                )
            )
            if as_of_date is None:
                statement = statement.where(DocumentVersion.legal_status == LegalStatus.EFFECTIVE.value)
            else:
                statement = statement.where(
                    DocumentVersion.legal_status.in_(
                        [
                            LegalStatus.EFFECTIVE.value,
                            LegalStatus.SUPERSEDED.value,
                            LegalStatus.EXPIRED.value,
                            LegalStatus.SCHEDULED.value,
                        ]
                    )
                )
            rows = session.execute(statement).all()

        results: list[dict] = []
        for chunk, version, document in rows:
            if version.effective_from and version.effective_from > target_date:
                continue
            if version.effective_to and version.effective_to < target_date:
                continue
            try:
                allowed_roles, allowed_units, classification = derive_security_acl(
                    document.access_level,
                    document.allowed_departments,
                    owner_unit=document.owner_department,
                )
            except ValueError:
                continue
            tenant_id = (version.metadata_json or {}).get("tenant_id")
            payload = {
                **chunk.metadata_json,
                "document_id": document.id,
                "version_id": version.id,
                "document_number": document.document_number,
                "title": document.title,
                "source_url": document.source_url,
                "tenant_id": tenant_id,
                "status": "published",
                "classification": classification,
                "allowed_roles": allowed_roles,
                "allowed_units": allowed_units,
                "valid_from": (version.effective_from.isoformat() if version.effective_from else None),
                "valid_to": (version.effective_to.isoformat() if version.effective_to else None),
                "legal_status": version.legal_status,
                "access_level": document.access_level,
                "allowed_departments": document.allowed_departments or [],
                "effective_from": (version.effective_from.isoformat() if version.effective_from else None),
                "effective_to": (version.effective_to.isoformat() if version.effective_to else None),
            }
            if not can_access_document(user, payload, as_of=target_date):
                continue
            results.append(
                {
                    "chunk_id": chunk.id,
                    "text": chunk.text,
                    "embedding_text": chunk.embedding_text,
                    "payload": payload,
                }
            )
        # Older ingests predate canonical neighbor metadata. Derive missing
        # links from authoritative PostgreSQL chunk order at read time so
        # context expansion works immediately and remains independent of the
        # Qdrant payload copy.
        by_version: dict[str, list[dict]] = {}
        for item in results:
            version_id = str(item["payload"]["version_id"])
            by_version.setdefault(version_id, []).append(item)
        for version_items in by_version.values():
            version_items.sort(
                key=lambda item: int(item["payload"].get("chunk_index", 0))
            )
            for index, item in enumerate(version_items):
                payload = item["payload"]
                payload.setdefault(
                    "previous_chunk_id",
                    version_items[index - 1]["chunk_id"] if index else None,
                )
                payload.setdefault(
                    "next_chunk_id",
                    (
                        version_items[index + 1]["chunk_id"]
                        if index + 1 < len(version_items)
                        else None
                    ),
                )
        return results

    def get_context_chunks(self, chunk_ids):
        """Load expansion chunks and canonical access metadata from PostgreSQL.

        Context expansion must never trust the Qdrant payload copy. This method
        deliberately reconstructs both the candidate and the policy payload
        from the authoritative relational rows.
        """
        from src.domain.schemas import Candidate, QdrantPayload
        from src.retrieval.context_expansion import AuthoritativeChunk

        requested = list(dict.fromkeys(str(item) for item in chunk_ids if item))
        if not requested:
            return {}
        with self.session_factory() as session:
            rows = session.execute(
                select(Chunk, DocumentVersion, Document)
                .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(Chunk.id.in_(requested))
            ).all()

        output = {}
        for chunk, version, document in rows:
            metadata = {
                **chunk.metadata_json,
                "document_id": document.id,
                "version_id": version.id,
                "document_number": document.document_number,
                "title": document.title,
                "source_url": document.source_url,
                "legal_status": version.legal_status,
                "access_level": document.access_level,
                "allowed_departments": document.allowed_departments or [],
            }
            public_scope = str(document.access_level).casefold() == "public"
            allowed_units = list(
                metadata.get("allowed_units")
                or (["*"] if public_scope else document.allowed_departments or [])
            )
            allowed_roles = list(metadata.get("allowed_roles") or ["*"])
            access_payload = QdrantPayload(
                tenant_id=str(
                    metadata.get("tenant_id")
                    or ("public" if public_scope else "hust")
                ),
                document_id=document.id,
                version_id=version.id,
                chunk_id=chunk.id,
                parent_chunk_id=metadata.get("parent_chunk_id"),
                previous_chunk_id=metadata.get("previous_chunk_id"),
                next_chunk_id=metadata.get("next_chunk_id"),
                owner_unit=document.owner_department,
                allowed_roles=allowed_roles,
                allowed_units=allowed_units,
                classification=str(metadata.get("classification") or "internal"),
                status="published",
                valid_from=version.effective_from or version.issued_date or date(1970, 1, 1),
                valid_to=version.effective_to,
                page=metadata.get("page"),
                section=metadata.get("section"),
                title=document.title,
                document_number=document.document_number,
                source_url=document.source_url,
                content_hash=chunk.content_hash or f"legacy:{chunk.id}",
                embedding_model=str(metadata.get("embedding_model") or "unknown"),
                embedding_version=str(metadata.get("embedding_version") or "1"),
                sparse_model=metadata.get("sparse_model"),
                sparse_version=metadata.get("sparse_version"),
                index_version=str(metadata.get("index_version") or "postgresql"),
            )
            candidate = Candidate(
                chunk_id=chunk.id,
                document_id=document.id,
                version_id=version.id,
                content=chunk.text,
                metadata=metadata,
                fusion_score=0.0,
            )
            output[chunk.id] = AuthoritativeChunk(
                candidate=candidate,
                access_payload=access_payload,
            )
        return output

    def list_published_chunks_for_index(self) -> list[dict]:
        """Return published chunks for rebuilding an ephemeral/local vector index."""
        with self.session_factory() as session:
            rows = session.execute(
                select(Chunk, DocumentVersion, Document)
                .join(DocumentVersion, Chunk.version_id == DocumentVersion.id)
                .join(Document, DocumentVersion.document_id == Document.id)
                .where(
                    DocumentVersion.processing_status.in_(
                        [
                            ProcessingStatus.PUBLISHED.value,
                            # Legacy rag_legacy schema values written by
                            # the original ingest path.
                            "indexed",
                            "Published",
                        ]
                    ),
                    DocumentVersion.legal_status.in_(
                        [
                            LegalStatus.EFFECTIVE.value,
                            LegalStatus.SCHEDULED.value,
                            LegalStatus.SUPERSEDED.value,
                            LegalStatus.EXPIRED.value,
                        ]
                    ),
                )
            ).all()
        output: list[dict] = []
        for chunk, version, document in rows:
            allowed_roles, allowed_units, classification = derive_security_acl(
                document.access_level,
                document.allowed_departments,
                owner_unit=document.owner_department,
            )
            output.append(
                {
                    "id": chunk.id,
                    "embedding_text": chunk.embedding_text,
                    "version_number": version.version_number,
                    "processing_status": version.processing_status,
                    "payload": {
                        **chunk.metadata_json,
                        "document_id": document.id,
                        "version_id": version.id,
                        "document_number": document.document_number,
                        "title": document.title,
                        "source_url": document.source_url,
                        "owner_unit": document.owner_department,
                        "tenant_id": (version.metadata_json or {}).get("tenant_id"),
                        "status": "published",
                        "classification": classification,
                        "allowed_roles": allowed_roles,
                        "allowed_units": allowed_units,
                        "valid_from": (
                            version.effective_from.isoformat()
                            if version.effective_from else None
                        ),
                        "valid_to": (
                            version.effective_to.isoformat()
                            if version.effective_to else None
                        ),
                        "legal_status": version.legal_status,
                    },
                }
            )
        return output

    def list_documents(self) -> list[dict]:
        with self.session_factory() as session:
            documents = list(session.scalars(select(Document).order_by(Document.created_at.desc())))
            output: list[dict] = []
            for document in documents:
                versions = session.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == document.id)
                    .order_by(DocumentVersion.version_number.desc())
                ).all()
                output.append(
                    {
                        "id": document.id,
                        "title": document.title,
                        "document_number": document.document_number,
                        "owner_department": document.owner_department,
                        "access_level": document.access_level,
                        "versions": [
                            {
                                "id": version.id,
                                "version_number": version.version_number,
                                "processing_status": version.processing_status,
                                "legal_status": version.legal_status,
                                "effective_from": version.effective_from,
                                "effective_to": version.effective_to,
                            }
                            for version in versions
                        ],
                    }
                )
            return output

    def create_audit_log(
        self,
        *,
        request_id: str,
        user: UserContext,
        action: str,
        outcome: str,
        query: str | None = None,
        resource_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> None:
        with self.session_factory() as session:
            session.add(
                AuditLog(
                    request_id=request_id,
                    user_id=user.user_id,
                    department=user.department,
                    action=action,
                    query=query,
                    resource_ids=resource_ids or [],
                    outcome=outcome,
                    metadata_json=metadata or {},
                )
            )
            session.commit()

    def save_feedback(
        self,
        *,
        request_id: str,
        user_id: str,
        rating: int,
        comment: str | None,
    ) -> str:
        with self.session_factory() as session:
            feedback = UserFeedback(
                request_id=request_id,
                user_id=user_id,
                rating=rating,
                comment=comment,
            )
            session.add(feedback)
            session.commit()
            session.refresh(feedback)
            return feedback.id

    def stats(self) -> dict[str, int]:
        with self.session_factory() as session:
            return {
                "documents": session.scalar(select(func.count(Document.id))) or 0,
                "versions": session.scalar(select(func.count(DocumentVersion.id))) or 0,
                "chunks": session.scalar(select(func.count(Chunk.id))) or 0,
            }

    # ── IngestionJob ────────────────────────────────────────────────────────────

    def create_ingestion_job(
        self,
        version_id: str,
        *,
        status: str = "received",
        parser_name: str | None = None,
    ) -> IngestionJob:
        with self.session_factory() as session:
            job = IngestionJob(
                version_id=version_id,
                status=status,
                parser_name=parser_name,
                started_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return job

    def update_ingestion_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        error_message: str | None = None,
        parser_warnings: list[str] | None = None,
        chunking_warnings: list[str] | None = None,
        section_count: int | None = None,
        chunk_count: int | None = None,
    ) -> IngestionJob | None:
        with self.session_factory() as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return None
            if status is not None:
                job.status = status
            if error_message is not None:
                job.error_message = error_message
            if parser_warnings is not None:
                job.parser_warnings = parser_warnings
            if chunking_warnings is not None:
                job.chunking_warnings = chunking_warnings
            if section_count is not None:
                job.section_count = section_count
            if chunk_count is not None:
                job.chunk_count = chunk_count
            if status in {"indexed", "failed"}:
                job.completed_at = datetime.now(UTC).replace(tzinfo=None)
            session.commit()
            session.refresh(job)
            return job

    def get_latest_job_for_version(self, version_id: str) -> IngestionJob | None:
        with self.session_factory() as session:
            return session.scalar(
                select(IngestionJob)
                .where(IngestionJob.version_id == version_id)
                .order_by(IngestionJob.started_at.desc())
            )

    # ── ApprovalRecord ─────────────────────────────────────────────────────────

    def create_approval_record(
        self,
        version_id: str,
        *,
        decision: str,
        reviewer_id: str,
        note: str | None = None,
        warnings_snapshot: list[str] | None = None,
    ) -> ApprovalRecord:
        with self.session_factory() as session:
            record = ApprovalRecord(
                version_id=version_id,
                decision=decision,
                reviewer_id=reviewer_id,
                note=note,
                warnings_snapshot=warnings_snapshot or [],
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_approval_history(self, version_id: str) -> list[ApprovalRecord]:
        with self.session_factory() as session:
            return list(
                session.scalars(
                    select(ApprovalRecord)
                    .where(ApprovalRecord.version_id == version_id)
                    .order_by(ApprovalRecord.decided_at.desc())
                )
            )

    # ── AccessPolicy ──────────────────────────────────────────────────────────

    def create_access_policy(
        self,
        access_level: str,
        *,
        allowed_roles: list[str] | None = None,
        allowed_units: list[str] | None = None,
        applies_to: str = "document",
        applies_to_ids: list[str] | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> AccessPolicy:
        with self.session_factory() as session:
            policy = AccessPolicy(
                access_level=access_level,
                allowed_roles=allowed_roles or [],
                allowed_units=allowed_units or [],
                applies_to=applies_to,
                applies_to_ids=applies_to_ids or [],
                valid_from=valid_from,
                valid_to=valid_to,
            )
            session.add(policy)
            session.commit()
            session.refresh(policy)
            return policy

    def list_applicable_policies(
        self,
        document_id: str | None = None,
        version_id: str | None = None,
        at: datetime | None = None,
    ) -> list[AccessPolicy]:
        with self.session_factory() as session:
            query = select(AccessPolicy)
            if at is not None:
                query = query.where(
                    (AccessPolicy.valid_from.is_(None) | (AccessPolicy.valid_from <= at))
                    & (AccessPolicy.valid_to.is_(None) | (AccessPolicy.valid_to >= at))
                )
            policies = list(session.scalars(query))
            result: list[AccessPolicy] = []
            for policy in policies:
                if policy.applies_to == "document" and document_id:
                    if document_id in (policy.applies_to_ids or []):
                        result.append(policy)
                elif policy.applies_to == "version" and version_id:
                    if version_id in (policy.applies_to_ids or []):
                        result.append(policy)
                elif policy.applies_to in {"section", "chunk"}:
                    pass  # phạm vi cấp section/chunk cần chunk_id cụ thể ở query time
                else:
                    result.append(policy)
            return result

    # ── DocumentRelation ────────────────────────────────────────────────────────

    def create_document_relation(
        self,
        source_document_id: str,
        target_document_id: str,
        relation_type: str,
        *,
        direction: str = "unidirectional",
        effective_from: date | None = None,
        metadata: dict | None = None,
    ) -> DocumentRelation:
        with self.session_factory() as session:
            relation = DocumentRelation(
                source_document_id=source_document_id,
                target_document_id=target_document_id,
                relation_type=relation_type,
                direction=direction,
                effective_from=effective_from,
                metadata_json=metadata or {},
            )
            session.add(relation)
            session.commit()
            session.refresh(relation)
            return relation

    def list_document_relations(
        self,
        document_id: str,
        *,
        relation_type: str | None = None,
    ) -> list[DocumentRelation]:
        with self.session_factory() as session:
            query = select(DocumentRelation).where(
                (DocumentRelation.source_document_id == document_id)
                | (DocumentRelation.target_document_id == document_id)
            )
            if relation_type:
                query = query.where(DocumentRelation.relation_type == relation_type)
            return list(session.scalars(query.order_by(DocumentRelation.created_at.desc())))
