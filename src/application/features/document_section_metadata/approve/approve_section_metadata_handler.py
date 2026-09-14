from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_section_metadata.approve.approve_section_metadata_command import (
    ApproveSectionMetadataCommand,
)
from src.application.features.document_section_metadata.common.section_metadata_draft_item import (
    SectionMetadataDraftItem,
)
from src.domain.enums.document_metadata_draft_status import (
    DocumentMetadataDraftStatus,
)
from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)


class ApproveSectionMetadataHandler(
    RequestHandler[
        ApproveSectionMetadataCommand,
        SectionMetadataDraftItem,
    ]
):
    def __init__(
        self,
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
        digitization_repository: (
            DocumentDigitizationRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._section_metadata_repository = (
            section_metadata_repository
        )

        self._digitization_repository = (
            digitization_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            ApproveSectionMetadataCommand
        ),
    ) -> SectionMetadataDraftItem:
        draft = await (
            self._section_metadata_repository
            .get_by_id(
                request.draft_id
            )
        )

        if draft is None:
            raise NotFoundException(
                "Section metadata draft "
                "not found."
            )

        if (
            draft.status
            != (
                DocumentMetadataDraftStatus
                .PENDING_REVIEW
            )
        ):
            raise ConflictException(
                "Section metadata draft "
                "has already been reviewed."
            )

        now = datetime.now(
            timezone.utc
        )

        draft.metadata = dict(
            request.metadata
        )

        draft.cross_references = [
            dict(item)
            for item
            in request.cross_references
        ]

        draft.status = (
            DocumentMetadataDraftStatus
            .APPROVED
        )

        draft.needs_human_review = False

        draft.rationale = None

        draft.reviewed_by = (
            request.reviewer_user_id
        )

        draft.reviewed_at = now
        draft.updated_at = now

        chunk_metadata = dict(
            draft.metadata
        )

        chunk_metadata[
            "cross_references"
        ] = [
            dict(item)
            for item
            in draft.cross_references
        ]

        chunk_metadata[
            "metadata_review_status"
        ] = (
            DocumentMetadataDraftStatus
            .APPROVED
            .value
        )

        chunk_metadata[
            "metadata_reviewed_at"
        ] = now.isoformat()

        await (
            self._digitization_repository
            .update_chunk_metadata(
                chunk_id=draft.chunk_id,
                metadata=chunk_metadata,
            )
        )

        await (
            self._section_metadata_repository
            .save(draft)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            SectionMetadataDraftItem
            .from_entity(draft)
        )