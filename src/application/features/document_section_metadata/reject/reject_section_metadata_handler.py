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
from src.application.features.document_section_metadata.common.section_metadata_draft_item import (
    SectionMetadataDraftItem,
)
from src.application.features.document_section_metadata.reject.reject_section_metadata_command import (
    RejectSectionMetadataCommand,
)
from src.domain.enums.document_metadata_draft_status import (
    DocumentMetadataDraftStatus,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)


class RejectSectionMetadataHandler(
    RequestHandler[
        RejectSectionMetadataCommand,
        SectionMetadataDraftItem,
    ]
):
    def __init__(
        self,
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._section_metadata_repository = (
            section_metadata_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            RejectSectionMetadataCommand
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

        reason = request.reason.strip()

        if not reason:
            raise ConflictException(
                "Rejection reason is required."
            )

        now = datetime.now(
            timezone.utc
        )

        draft.status = (
            DocumentMetadataDraftStatus
            .REJECTED
        )

        draft.rationale = reason

        draft.reviewed_by = (
            request.reviewer_user_id
        )

        draft.reviewed_at = now
        draft.updated_at = now

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