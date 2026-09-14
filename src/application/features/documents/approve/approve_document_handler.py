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
from src.application.features.documents.approve.approve_document_command import (
    ApproveDocumentCommand,
)
from src.application.features.documents.approve.approve_document_result import (
    ApproveDocumentResult,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.schemas import ProcessingStatus


class ApproveDocumentHandler(
    RequestHandler[
        ApproveDocumentCommand,
        ApproveDocumentResult,
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
        request: ApproveDocumentCommand,
    ) -> ApproveDocumentResult:
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

        # Strict gate (Phase 3b): only PENDING_APPROVAL can be approved.
        # Reviewer must first call /complete-review.
        if current != ProcessingStatus.PENDING_APPROVAL:
            raise ConflictException(
                f"Cannot approve from status '{current.value}'. "
                "Document must be in 'pending_approval' state. "
                "Use /complete-review first."
            )

        now = datetime.now(timezone.utc)
        version.processing_status = ProcessingStatus.APPROVED

        await (
            self._document_version_repository.update(
                version
            )
        )
        await self._unit_of_work.save_changes()

        return ApproveDocumentResult(
            version_id=version.id,
            status=ProcessingStatus.APPROVED,
            approved_at=now,
        )
