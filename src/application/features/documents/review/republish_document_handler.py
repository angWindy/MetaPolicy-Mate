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
from src.application.features.documents.review.republish_document_command import (
    RepublishDocumentCommand,
)
from src.application.features.documents.review.republish_document_result import (
    RepublishDocumentResult,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.domain.schemas import ProcessingStatus


class RepublishDocumentHandler(
    RequestHandler[
        RepublishDocumentCommand,
        RepublishDocumentResult,
    ]
):
    def __init__(
        self,
        document_version_repository: (
            DocumentVersionRepository
        ),
        user_repository: UserRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_version_repository = (
            document_version_repository
        )
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: RepublishDocumentCommand,
    ) -> RepublishDocumentResult:
        # Verify admin
        admin = await self._user_repository.get_by_id(
            request.admin_id
        )
        if admin is None:
            raise ForbiddenException(
                "Admin not found."
            )
        if not admin.is_admin:
            raise ForbiddenException(
                "Only admin can republish."
            )

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

        if current != ProcessingStatus.REJECTED:
            raise ConflictException(
                f"Cannot republish from status '{current.value}'. "
                "Only REJECTED versions can be republished."
            )

        now = datetime.now(timezone.utc)
        version.processing_status = (
            ProcessingStatus.PENDING_REVIEW
        )
        version.review_notes = request.notes
        version.reviewed_by = request.admin_id
        version.reviewed_at = now

        await (
            self._document_version_repository.update(
                version
            )
        )
        await self._unit_of_work.save_changes()

        return RepublishDocumentResult(
            version_id=version.id,
            status=ProcessingStatus.PENDING_REVIEW,
            reviewed_at=now,
        )
