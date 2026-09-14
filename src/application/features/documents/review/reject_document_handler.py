from datetime import datetime, timezone

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
from src.application.features.documents.review.reject_document_command import (
    RejectDocumentCommand,
)
from src.application.features.documents.review.reject_document_result import (
    RejectDocumentResult,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.schemas import ProcessingStatus


class RejectDocumentHandler(
    RequestHandler[
        RejectDocumentCommand,
        RejectDocumentResult,
    ]
):
    def __init__(
        self,
        document_version_repository: (
            DocumentVersionRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_version_repository = (
            document_version_repository
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: RejectDocumentCommand,
    ) -> RejectDocumentResult:
        version = await (
            self._document_version_repository.get_by_id(
                request.version_id
            )
        )
        if version is None:
            raise NotFoundException(
                "Document version not found."
            )

        current = ProcessingStatus(
            version.processing_status.value
            if hasattr(
                version.processing_status, "value"
            )
            else str(version.processing_status)
        )

        if current not in (
            ProcessingStatus.PENDING_REVIEW,
            ProcessingStatus.PENDING_APPROVAL,
        ):
            raise ConflictException(
                f"Cannot reject from status '{current.value}'."
            )

        now = datetime.now(timezone.utc)
        version.processing_status = ProcessingStatus.REJECTED
        version.review_notes = request.notes
        version.reviewed_by = request.reviewer_id
        version.reviewed_at = now

        await (
            self._document_version_repository.update(
                version
            )
        )
        await self._unit_of_work.save_changes()

        return RejectDocumentResult(
            version_id=version.id,
            status=ProcessingStatus.REJECTED,
            reviewed_at=now,
        )
