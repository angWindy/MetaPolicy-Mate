"""AutoApproveReview handler.

Fast-track admin approval: re-run :class:`MetadataQualityGate` and flip
``PENDING_REVIEW → APPROVED`` when the gate passes.

The handler is a thin orchestration layer:

1. Load the version + its parent document.
2. Run :class:`MetadataQualityGate` on the document.
3. If ``needs_human_review=True`` return a ``PENDING_REVIEW`` result
   with the gate verdict so the admin UI can render a fix list.
4. Otherwise transition the version to ``APPROVED`` and commit.

Note: this handler does NOT call
:class:`src.application.features.document_digitization.digitize.
digitize_document_handler.DigitizeDocumentHandler` afterwards. The
existing ``POST /admin/documents/{version_id}/index`` endpoint already
triggers that — admins call it explicitly after auto-approve to push
chunks into Qdrant.
"""

from __future__ import annotations

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
from src.application.common.metadata_quality_gate import (
    MetadataQualityGate,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.documents.review.auto_approve_review_command import (
    AutoApproveReviewCommand,
)
from src.application.features.documents.review.auto_approve_review_result import (
    AutoApproveReviewResult,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.domain.schemas import ProcessingStatus


class AutoApproveReviewHandler(
    RequestHandler[
        AutoApproveReviewCommand,
        AutoApproveReviewResult,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_version_repository: (
            DocumentVersionRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_repository = document_repository
        self._document_version_repository = (
            document_version_repository
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: AutoApproveReviewCommand,
    ) -> AutoApproveReviewResult:
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

        # Strict gate: only PENDING_REVIEW can be auto-approved.
        # REVIEW_REQUIRED (legacy parse-fail state) and
        # PENDING_APPROVAL (already passed manual review) must follow
        # their respective existing flows.
        if current != ProcessingStatus.PENDING_REVIEW:
            raise ConflictException(
                f"Cannot auto-approve from status '{current.value}'. "
                f"Expected '{ProcessingStatus.PENDING_REVIEW.value}'. "
                "Use /complete-review first if status is "
                "PENDING_APPROVAL."
            )

        document = await (
            self._document_repository.get_by_id(
                version.document_id
            )
        )
        if document is None:
            raise NotFoundException(
                "Parent document not found for this version."
            )

        # Re-evaluate the gate against the *current* document row.
        # The metadata may have been edited by an admin in the time
        # between the original ingest and this auto-approve attempt.
        gate_result = MetadataQualityGate.evaluate(document)

        if gate_result.needs_human_review:
            # Gate still fails — return a PENDING_REVIEW result with
            # the rationale so the UI can render a fix list. We do NOT
            # flip the status (it stays PENDING_REVIEW) so the version
            # remains visible in the review queue.
            return AutoApproveReviewResult(
                version_id=version.id,
                status=ProcessingStatus.PENDING_REVIEW,
                validation_result=gate_result.to_dict(),
                approved_at=None,
            )

        # Gate passes — fast-track to APPROVED. The admin can then
        # trigger ``/index`` to push chunks to Qdrant.
        now = datetime.now(timezone.utc)
        version.processing_status = ProcessingStatus.APPROVED
        version.review_notes = (
            (version.review_notes or "")
            + ("\n" if version.review_notes else "")
            + f"[auto-approve] {request.notes or ''}".rstrip()
        )
        version.reviewed_by = request.admin_id
        version.reviewed_at = now

        await (
            self._document_version_repository.update(version)
        )
        await self._unit_of_work.save_changes()

        return AutoApproveReviewResult(
            version_id=version.id,
            status=ProcessingStatus.APPROVED,
            validation_result=gate_result.to_dict(),
            approved_at=now,
        )
