from datetime import datetime, timezone

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
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
from src.application.features.documents.review.complete_review_command import (
    CompleteReviewCommand,
)
from src.application.features.documents.review.complete_review_result import (
    CompleteReviewResult,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.schemas import ProcessingStatus
from src.persistence.tenant.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)


class CompleteReviewHandler(
    RequestHandler[
        CompleteReviewCommand,
        CompleteReviewResult,
    ]
):
    def __init__(
        self,
        document_version_repository: (
            DocumentVersionRepository
        ),
        user_repository: SqlAlchemyUserRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_version_repository = (
            document_version_repository
        )
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: CompleteReviewCommand,
    ) -> CompleteReviewResult:
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

        if current != ProcessingStatus.PENDING_REVIEW:
            raise ConflictException(
                f"Cannot complete review from status '{current.value}'. "
                f"Expected '{ProcessingStatus.PENDING_REVIEW.value}'."
            )

        # Verify reviewer exists
        reviewer = await self._user_repository.get_by_id(
            request.reviewer_id
        )
        if reviewer is None:
            raise ForbiddenException(
                "Reviewer not found."
            )

        now = datetime.now(timezone.utc)
        version.processing_status = (
            ProcessingStatus.PENDING_APPROVAL
        )
        version.review_notes = request.notes
        version.reviewed_by = request.reviewer_id
        version.reviewed_at = now

        await (
            self._document_version_repository.update(
                version
            )
        )
        await self._unit_of_work.save_changes()

        return CompleteReviewResult(
            version_id=version.id,
            status=ProcessingStatus.PENDING_APPROVAL,
            reviewed_at=now,
        )
