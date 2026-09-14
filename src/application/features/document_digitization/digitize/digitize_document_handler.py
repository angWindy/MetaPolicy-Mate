from typing import Literal

import hashlib

from datetime import (
    datetime,
    timezone,
)
from uuid import (
    UUID,
    uuid4,
)

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.document_digitization_service import (
    DocumentDigitizationService,
)
from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.metadata_quality_gate import (
    MetadataQualityGate,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_digitization.common.document_digitization_item import (
    DocumentDigitizationItem,
)
from src.application.features.document_digitization.digitize.digitize_document_command import (
    DigitizeDocumentCommand,
)
from src.domain.entities.document_chunk import (
    DocumentChunk,
)
from src.domain.entities.document_ingestion_job import (
    DocumentIngestionJob,
)
from src.domain.entities.document_section import (
    DocumentSection,
)
from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)
from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.schemas import ProcessingStatus
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.application.common.interfaces.rag_index_service import (
    RagIndexService,
)

class DigitizeDocumentHandler(
    RequestHandler[
        DigitizeDocumentCommand,
        DocumentDigitizationItem,
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),

        document_version_repository: (
            DocumentVersionRepository
        ),

        digitization_repository: (
            DocumentDigitizationRepository
        ),

        department_repository: (
            DepartmentRepository
        ),

        document_department_repository: (
            DocumentDepartmentRepository
        ),

        digitization_service: (
            DocumentDigitizationService
        ),

        rag_index_service: (
            RagIndexService
        ),

        file_storage: FileStorage,

        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._document_version_repository = (
            document_version_repository
        )

        self._digitization_repository = (
            digitization_repository
        )

        self._department_repository = (
            department_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

        self._digitization_service = (
            digitization_service
        )

        self._rag_index_service = (
            rag_index_service
        )

        self._file_storage = (
            file_storage
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: DigitizeDocumentCommand,
    ) -> DocumentDigitizationItem:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document not found."
            )

        version = await (
            self
            ._document_version_repository
            .get_by_id_for_update(
                request.version_id
            )
        )

        if version is None:
            raise NotFoundException(
                "Document version not found."
            )

        if (
            version.processing_status
            == DocumentProcessingStatus
            .DANG_SO_HOA
        ):
            raise ConflictException(
                "Document version is already "
                "being digitized."
            )

        if (
            version.processing_status
            == DocumentProcessingStatus
            .DA_SO_HOA
        ):
            raise ConflictException(
                "Document version has already "
                "been digitized. Replace the "
                "source to create a new version "
                "before digitizing again."
            )
        #
        # BẮT BUỘC:
        # version phải thuộc đúng document.
        #
        if (
            version.document_id
            != document.id
        ):
            raise ConflictException(
                "Document version does not "
                "belong to this document."
            )

        department_ids = await (
            self
            ._document_department_repository
            .get_department_ids(
                document.id
            )
        )

        department_codes: list[
            str
        ] = []

        for department_id in (
            department_ids
        ):
            department = await (
                self._department_repository
                .get_by_id(
                    department_id
                )
            )

            if department is not None:
                department_codes.append(
                    department.code
                    .strip()
                    .upper()
                )

        if (
            document.access_scope
            == DocumentAccessScope.DEPARTMENT
            and not department_codes
        ):
            raise ConflictException(
                "Department-restricted "
                "document has no allowed "
                "department."
            )

        allowed_units = (
            ["*"]
            if (
                document.access_scope
                == DocumentAccessScope.PUBLIC
            )
            else department_codes
        )

        if (
            version.processing_status
            == (
                DocumentProcessingStatus
                .DANG_SO_HOA
            )
        ):
            raise ConflictException(
                "Document version is "
                "already being digitized."
            )

        now = datetime.now(
            timezone.utc
        )

        job = DocumentIngestionJob(
            id=uuid4(),

            version_id=(
                version.id
            ),

            status="PROCESSING",

            warnings=[],

            error_message=None,

            section_count=0,

            chunk_count=0,

            started_at=now,

            completed_at=None,
        )

        await (
            self._digitization_repository
            .add_job(job)
        )

        version.processing_status = (
            DocumentProcessingStatus
            .DANG_SO_HOA
        )

        await (
            self
            ._document_version_repository
            .update(version)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        try:
            content = await (
                self._file_storage
                .download(
                    version.object_key
                )
            )

            result = await (
                self._digitization_service
                .digitize(
                    document_id=(
                        str(document.id)
                    ),

                    version_id=(
                        str(version.id)
                    ),

                    filename=(
                        version.source_filename
                    ),

                    content=content,

                    document_number=(
                        document.document_number
                    ),

                    title=document.title,

                    issued_by=(
                        document.issued_by
                    ),

                    issued_date=(
                        document.issued_date
                    ),

                    effective_date=(
                        document.effective_date
                    ),

                    version_number=(
                        version.version_number
                    ),

                    ocr_engine=(
                        request.ocr_engine
                    ),
                )
            )

            sections: list[
                DocumentSection
            ] = []

            section_ids: list[
                UUID
            ] = []

            for section in (
                result.sections
            ):
                section_id = uuid4()

                section_ids.append(
                    section_id
                )

                sections.append(
                    DocumentSection(
                        id=section_id,

                        version_id=(
                            version.id
                        ),

                        section_type=(
                            section
                            .section_type
                        ),

                        section_number=(
                            section
                            .section_number
                        ),

                        heading=(
                            section.heading
                        ),

                        heading_path=(
                            section
                            .heading_path
                        ),

                        content=(
                            section.content
                        ),

                        page=(
                            section.page
                        ),

                        sort_order=(
                            section.sort_order
                        ),
                    )
                )

            chunks: list[
                DocumentChunk
            ] = []

            for chunk in result.chunks:
                section_id = None

                if (
                    chunk.section_index
                    is not None
                    and 0
                    <= chunk.section_index
                    < len(section_ids)
                ):
                    section_id = (
                        section_ids[
                            chunk.section_index
                        ]
                    )

                content_hash = (
                    hashlib.sha256(
                        chunk.text.encode(
                            "utf-8"
                        )
                    ).hexdigest()
                )

                chunk_metadata = dict(
                    chunk.metadata
                )

                chunk_metadata[
                    "access_scope"
                ] = (
                    document.access_scope.value
                )

                chunk_metadata[
                    "allowed_units"
                ] = list(
                    allowed_units
                )

                chunks.append(
                    DocumentChunk(
                        id=UUID(
                            chunk.id
                        ),

                        version_id=(
                            version.id
                        ),

                        section_id=(
                            section_id
                        ),

                        chunk_index=(
                            chunk.chunk_index
                        ),

                        text=chunk.text,

                        embedding_text=(
                            chunk.embedding_text
                        ),

                        content_hash=(
                            content_hash
                        ),

                        metadata=(
                            chunk_metadata
                        ),
                    )
                )

            await (
                self
                ._digitization_repository
                .replace_content(
                    version_id=(
                        version.id
                    ),
                    sections=sections,
                   chunks=chunks,
                )
            )

            # Commit PostgreSQL trước.
            # Neon là source-of-truth.
            await (
                self._unit_of_work
                .save_changes()
            )

            # Metadata quality gate (2026-09-06 metadata cleanup).
            # Evaluates document_number / title / issued_by / dates;
            # when ANY required field is missing the version is
            # diverted to PENDING_REVIEW so an admin can complete the
            # metadata manually before RAG exposes the chunks.
            # Chunks remain in Neon (so admins can read the content
            # during review) but we skip the Qdrant push and the
            # ``DA_SO_HOA`` (INDEXED) status flip. The gate rationale
            # is appended to ``job.warnings`` so the admin queue can
            # render a fix list without re-running the gate.
            quality_result = (
                MetadataQualityGate
                .evaluate(document)
            )

            if quality_result.needs_human_review:
                version.processing_status = (
                    ProcessingStatus.PENDING_REVIEW
                )
                await (
                    self
                    ._document_version_repository
                    .update(version)
                )

                completed_at = datetime.now(
                    timezone.utc
                )

                job.status = "PENDING_REVIEW"
                job.warnings = list(
                    result.warnings
                ) + list(
                    quality_result.rationale
                )
                job.section_count = len(
                    sections
                )
                job.chunk_count = len(
                    chunks
                )
                job.completed_at = completed_at
                await (
                    self
                    ._digitization_repository
                    .update_job(job)
                )
                await (
                    self
                    ._unit_of_work
                    .save_changes()
                )

                return DocumentDigitizationItem(
                    version_id=version.id,
                    status=job.status,
                    section_count=job.section_count,
                    chunk_count=job.chunk_count,
                    warnings=job.warnings,
                    error_message=None,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )

            # Sau khi chunks đã tồn tại
            # chắc chắn ở Neon mới tạo
            # search index trong Qdrant.
            await (
                self._rag_index_service
                .index_chunks(
                    document=document,
                    version=version,
                    chunks=chunks,
                    allowed_units=(
                        allowed_units
                    ),
                )
            )

            version.processing_status = (
                DocumentProcessingStatus
                .DA_SO_HOA
            )

            await (
                self
                ._document_version_repository
                .update(version)
            )

            completed_at = datetime.now(
                timezone.utc
            )

            job.status = "SUCCEEDED"

            job.warnings = list(
                result.warnings
            )

            job.section_count = len(
                sections
            )

            job.chunk_count = len(
                chunks
            )

            job.completed_at = (
                completed_at
            )

            await (
                self
                ._digitization_repository
                .update_job(job)
            )

            await (
                self._unit_of_work
                .save_changes()
            )

            return DocumentDigitizationItem(
                version_id=version.id,

                status=job.status,

                section_count=(
                    job.section_count
                ),

                chunk_count=(
                    job.chunk_count
                ),

                warnings=job.warnings,

                error_message=None,

                started_at=(
                    job.started_at
                ),

                completed_at=(
                    job.completed_at
                ),
            )

        except Exception as exc:
            version.processing_status = (
                DocumentProcessingStatus
                .SO_HOA_THAT_BAI
            )

            await (
                self
                ._document_version_repository
                .update(version)
            )

            job.status = "FAILED"

            job.error_message = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            job.completed_at = (
                datetime.now(
                    timezone.utc
                )
            )

            await (
                self
                ._digitization_repository
                .update_job(job)
            )

            await (
                self._unit_of_work
                .save_changes()
            )

            raise