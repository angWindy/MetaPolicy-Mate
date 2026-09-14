from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.section_metadata_extraction_service import (
    SectionMetadataExtractionService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_section_metadata.common.section_metadata_draft_item import (
    SectionMetadataDraftItem,
)
from src.application.features.document_section_metadata.extract.extract_section_metadata_command import (
    ExtractSectionMetadataCommand,
)
from src.domain.entities.document_section_metadata_draft import (
    DocumentSectionMetadataDraft,
)
from src.domain.enums.document_metadata_draft_status import (
    DocumentMetadataDraftStatus,
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
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class ExtractSectionMetadataHandler(
    RequestHandler[
        ExtractSectionMetadataCommand,
        list[SectionMetadataDraftItem],
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
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
        section_metadata_extraction_service: (
            SectionMetadataExtractionService
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._version_repository = (
            document_version_repository
        )

        self._digitization_repository = (
            digitization_repository
        )

        self._section_metadata_repository = (
            section_metadata_repository
        )

        self._extraction_service = (
            section_metadata_extraction_service
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            ExtractSectionMetadataCommand
        ),
    ) -> list[
        SectionMetadataDraftItem
    ]:
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
            self._version_repository
            .get_by_id(
                request.version_id
            )
        )

        if version is None:
            raise NotFoundException(
                "Document version not found."
            )

        if (
            version.document_id
            != document.id
        ):
            raise ConflictException(
                "Document version does not "
                "belong to this document."
            )

        if (
            version.processing_status
            != (
                DocumentProcessingStatus
                .DA_SO_HOA
            )
        ):
            raise ConflictException(
                "Document version must be "
                "digitized before section "
                "metadata extraction."
            )

        chunks = await (
            self._digitization_repository
            .get_chunks(
                version.id
            )
        )

        if not chunks:
            raise ConflictException(
                "Digitized chunks were not found."
            )

        results: list[
            SectionMetadataDraftItem
        ] = []

        for chunk in chunks:
            existing = await (
                self._section_metadata_repository
                .get_by_chunk_id(
                    chunk.id
                )
            )

            if (
                existing is not None
                and existing.status
                == (
                    DocumentMetadataDraftStatus
                    .APPROVED
                )
            ):
                results.append(
                    SectionMetadataDraftItem
                    .from_entity(existing)
                )

                continue

            extraction = await (
                self._extraction_service
                .extract(
                    filename=(
                        version.source_filename
                    ),
                    text=chunk.text,
                    base_metadata=(
                        chunk.metadata
                    ),
                )
            )

            now = datetime.now(
                timezone.utc
            )

            if existing is None:
                draft = (
                    DocumentSectionMetadataDraft(
                        id=uuid4(),
                        document_id=(
                            document.id
                        ),
                        version_id=(
                            version.id
                        ),
                        section_id=(
                            chunk.section_id
                        ),
                        chunk_id=(
                            chunk.id
                        ),
                        metadata=dict(
                            extraction.metadata
                        ),
                        cross_references=[
                            dict(item)
                            for item
                            in (
                                extraction
                                .cross_references
                            )
                        ],
                        needs_human_review=(
                            extraction
                            .needs_human_review
                        ),
                        rationale=(
                            extraction.rationale
                        ),
                        status=(
                            DocumentMetadataDraftStatus
                            .PENDING_REVIEW
                        ),
                        reviewed_by=None,
                        reviewed_at=None,
                        created_at=now,
                        updated_at=None,
                    )
                )
            else:
                draft = existing

                draft.section_id = (
                    chunk.section_id
                )

                draft.metadata = dict(
                    extraction.metadata
                )

                draft.cross_references = [
                    dict(item)
                    for item
                    in (
                        extraction
                        .cross_references
                    )
                ]

                draft.needs_human_review = (
                    extraction
                    .needs_human_review
                )

                draft.rationale = (
                    extraction.rationale
                )

                draft.status = (
                    DocumentMetadataDraftStatus
                    .PENDING_REVIEW
                )

                draft.reviewed_by = None
                draft.reviewed_at = None
                draft.updated_at = now

            await (
                self._section_metadata_repository
                .save(draft)
            )

            results.append(
                SectionMetadataDraftItem
                .from_entity(draft)
            )

        await (
            self._unit_of_work
            .save_changes()
        )

        return results