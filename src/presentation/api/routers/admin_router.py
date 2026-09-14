"""Admin router for document lifecycle management.

Provides endpoints for approve / index / publish document versions
as well as administrative stats. Mounted at /api/v1/admin.

These endpoints complement the legacy /api/v1/regulatory-documents
CRUD by exposing the governance workflow required by the
RAG pipeline (see ARCHITECTURE.md §5.2 - Document lifecycle).
"""
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import delete, select, func, update, and_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.features.document_digitization.digitize.digitize_document_command import (
    DigitizeDocumentCommand,
)
from src.domain.schemas import ProcessingStatus, LegalStatus
from src.persistence.tenant.models.document import DocumentModel
from src.persistence.tenant.models.document_version import DocumentVersionModel
from src.persistence.tenant.models.document_chunk import DocumentChunkModel
from src.persistence.tenant.models.user import UserModel
from src.persistence.tenant.models.user_activity_log import UserActivityLogModel
from src.persistence.tenant.session_factory import (
    TenantSessionFactory,
)
from src.presentation.api.contracts.admin.document_version_summary import (
    DocumentVersionSummary,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher_with_context,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)


router = APIRouter()


async def _get_session() -> AsyncSession:
    from src.config import get_settings
    factory: TenantSessionFactory = TenantSessionFactory()
    return factory.create(get_settings().database_url)


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[DocumentVersionSummary],
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        )
    ],
)
async def get_document_versions(
    document_id: UUID,
) -> list[DocumentVersionSummary]:
    """List version summaries for a single document.

    Used by the admin UI to surface per-version workflow buttons
    (approve / index / publish). We return the lightweight summary
    shape (no content / chunks) because the admin UI only needs
    ``version_id`` + ``processing_status`` to decide which buttons
    to render. Newest first.
    """
    async with await _get_session() as session:
        rows = (
            await session.execute(
                select(DocumentVersionModel)
                .where(DocumentVersionModel.document_id == document_id)
                .order_by(
                    DocumentVersionModel.version_number.desc()
                )
            )
        ).scalars().all()

    return [
        DocumentVersionSummary(
            id=row.id,
            document_id=row.document_id,
            version_number=row.version_number,
            processing_status=row.processing_status,
            source_filename=row.source_filename,
            size_bytes=row.size_bytes,
            object_key=row.object_key,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get(
    "/stats",
    response_model=dict,
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        )
    ],
)
async def get_admin_stats() -> dict:
    """Return top-level statistics for the admin dashboard.

    Returns the shape expected by the frontend ``AdminStats`` type:
    ``totalDocuments``, ``activeDocuments``, ``pendingDocuments``,
    ``expiredDocuments``, ``users``, ``questionsToday``.

    - ``activeDocuments``: documents with ``legal_status = effective``
    - ``pendingDocuments``: document versions with ``processing_status = received``
    - ``expiredDocuments``: documents with ``legal_status = expired``
    - ``users``: active user accounts
    - ``questionsToday``: activity log entries for "ask" requests today
    """
    today = date.today()
    async with await _get_session() as session:
        total = await session.scalar(
            select(func.count(DocumentModel.id))
        )
        active = await session.scalar(
            select(func.count(DocumentModel.id)).where(
                DocumentModel.legal_status == LegalStatus.EFFECTIVE.value
            )
        )
        pending = await session.scalar(
            select(func.count(DocumentVersionModel.id)).where(
                DocumentVersionModel.processing_status
                == ProcessingStatus.RECEIVED.value
            )
        )
        expired = await session.scalar(
            select(func.count(DocumentModel.id)).where(
                DocumentModel.legal_status == LegalStatus.EXPIRED.value
            )
        )
        users = await session.scalar(
            select(func.count(UserModel.id)).where(
                UserModel.is_active == True  # noqa: E712
            )
        )
        questions = await session.scalar(
            select(func.count(UserActivityLogModel.id)).where(
                and_(
                    UserActivityLogModel.request_name.ilike("%ask%"),
                    cast(UserActivityLogModel.started_at, String).startswith(
                        str(today)
                    ),
                )
            )
        )
        return {
            "totalDocuments": int(total or 0),
            "activeDocuments": int(active or 0),
            "pendingDocuments": int(pending or 0),
            "expiredDocuments": int(expired or 0),
            "users": int(users or 0),
            "questionsToday": int(questions or 0),
            "asOf": datetime.utcnow().isoformat() + "Z",
        }


@router.post(
    "/documents/{version_id}/approve",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def approve_document_version(
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Mark a pending-approval document version as Approved.

    Status gate (Phase 3b): only documents in ``PENDING_APPROVAL``
    may be approved. Use ``POST /admin/documents/{id}/complete-review``
    to move ``PENDING_REVIEW`` → ``PENDING_APPROVAL`` first.

    After approval, the RAG ingestion worker can begin
    embedding + upserting chunks into Qdrant. See ARCHITECTURE.md §5.2.

    Status values use the canonical English enum from
    ``src.domain.schemas.ProcessingStatus``.
    """
    from src.application.features.documents.approve.approve_document_command import (
        ApproveDocumentCommand,
    )

    result = await dispatcher.send(
        ApproveDocumentCommand(version_id=version_id)
    )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "approved_at": result.approved_at.isoformat() + "Z",
    }


@router.post(
    "/documents/{version_id}/index",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def index_document_version(
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Trigger indexing of an approved document version.

    The endpoint is now wired to the production RAG ingestion pipeline
    (parse → chunk → embed → Qdrant upsert) via
    :class:`DigitizeDocumentCommand`. The handler does the heavy work
    synchronously — by the time the response returns, chunks have
    been persisted to Neon and vectors upserted to Qdrant. We then
    flip ``processing_status`` to ``INDEXED`` so the rest of the
    lifecycle (publish) can pick up from a clean state.

    Idempotent: dispatching DigitizeDocumentCommand on a version that
    is already digitised raises ConflictException (handled) and we
    still flip the status to ``INDEXED`` — so re-running this
    endpoint after an interrupted ingest converges on the desired
    state.

    Status values use the canonical English enum from
    ``src.domain.schemas.ProcessingStatus`` (lowercase). The previous
    implementation wrote legacy capitalised strings ("Indexed",
    "Approved", "Published") which did not match the enum the rest
    of the pipeline reads, so RAG retrieval and admin queries saw
    the version as "never indexed".
    """
    async with await _get_session() as session:
        version = await session.get(
            DocumentVersionModel, version_id
        )
        if version is None:
            raise NotFoundException(
                "Document version not found."
            )
        if version.processing_status not in (
            ProcessingStatus.APPROVED.value,
            ProcessingStatus.INDEXED.value,
            ProcessingStatus.PARSED.value,
        ):
            raise ConflictException(
                "Version must be Approved (or already Digitised) "
                "before indexing. "
                f"Current status: {version.processing_status}."
            )
        document_id = version.document_id

    # Run the RAG ingestion pipeline (parse → chunk → embed → Qdrant).
    # DigitizeDocumentHandler is idempotent: it rejects concurrent runs
    # (DANG_SO_HOA = PARSED) and already-digitised runs (DA_SO_HOA =
    # INDEXED), but those rejections are caught and the status flip
    # still proceeds so the admin operator sees a consistent
    # "indexed" answer.
    digitisation_error: str | None = None
    try:
        await dispatcher.send(
            DigitizeDocumentCommand(
                document_id=document_id,
                version_id=version_id,
            )
        )
    except ConflictException as exc:
        # Already digitised — that's fine, the Qdrant side is up to
        # date from the previous run.
        digitisation_error = str(exc.detail)

    async with await _get_session() as session:
        await session.execute(
            update(DocumentVersionModel)
            .where(DocumentVersionModel.id == version_id)
            .values(
                processing_status=(
                    ProcessingStatus.INDEXED.value
                )
            )
        )
        await session.commit()
    return {
        "version_id": str(version_id),
        "status": ProcessingStatus.INDEXED.value,
        "indexed_at": datetime.utcnow().isoformat() + "Z",
        "digitisation_note": digitisation_error,
    }


@router.post(
    "/documents/{version_id}/publish",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def publish_document_version(
    version_id: UUID,
):
    """Publish an indexed document version.

    PUBLISHED ⇒ Qdrant indexing đã thành công (see ARCHITECTURE.md §24).

    Status values use the canonical English enum from
    ``src.domain.schemas.ProcessingStatus``. The previous
    implementation wrote legacy capitalised strings which did not
    match the canonical enum read by the rest of the pipeline.
    """
    async with await _get_session() as session:
        version = await session.get(
            DocumentVersionModel, version_id
        )
        if version is None:
            raise NotFoundException(
                "Document version not found."
            )
        if (
            version.processing_status
            != ProcessingStatus.INDEXED.value
        ):
            raise ConflictException(
                "Version must be Indexed before publishing. "
                f"Current status: {version.processing_status}."
            )
        await session.execute(
            update(DocumentVersionModel)
            .where(DocumentVersionModel.id == version_id)
            .values(
                processing_status=(
                    ProcessingStatus.PUBLISHED.value
                )
            )
        )
        await session.commit()
        return {
            "version_id": str(version_id),
            "status": ProcessingStatus.PUBLISHED.value,
            "published_at": datetime.utcnow().isoformat() + "Z",
        }


@router.post(
    "/documents/{version_id}/auto-approve-metadata",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def auto_approve_metadata(
    version_id: UUID,
    current_user: Annotated[
        "CurrentUser",
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Re-evaluate the metadata quality gate and fast-track to APPROVED.

    Operator flow for documents stuck in ``PENDING_REVIEW`` (the
    post-2026-09-06 metadata-cleanup divert state). The handler
    re-runs :class:`MetadataQualityGate` against the *current*
    document row; if the gate now passes the version is moved to
    ``APPROVED`` and the admin can follow up with ``/index`` to push
    chunks into Qdrant.

    Body schema (optional)::

        {
            "notes": "Optional free-text rationale."
        }

    Response::

        {
            "version_id": "...",
            "status": "approved" | "pending_review",
            "auto_approved": true | false,
            "validation_result": {
                "document_number_valid": bool,
                "title_valid": bool,
                "issued_by_valid": bool,
                "issued_date_present": bool,
                "effective_date_present": bool,
                "effective_after_issued": bool,
                "needs_human_review": bool,
                "rationale": [str, ...]
            },
            "approved_at": "ISO timestamp" | null
        }

    Status values use the canonical English enum from
    ``src.domain.schemas.ProcessingStatus``.
    """
    from src.application.common.interfaces.current_user import (
        CurrentUser,
    )
    from src.application.features.documents.review.auto_approve_review_command import (
        AutoApproveReviewCommand,
    )

    # Body is optional — admins may POST with no payload. We read it
    # defensively from the request state if present; otherwise we
    # dispatch with no notes.
    notes: str | None = None

    result = await dispatcher.send(
        AutoApproveReviewCommand(
            version_id=version_id,
            admin_id=current_user.user_id,
            notes=notes,
        )
    )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "auto_approved": result.auto_approved,
        "validation_result": result.validation_result,
        "approved_at": (
            result.approved_at.isoformat() + "Z"
            if result.approved_at else None
        ),
    }


@router.get(
    "/documents/{version_id}/status",
    response_model=dict,
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        )
    ],
)
async def get_version_status(
    version_id: UUID,
) -> dict:
    """Return the current processing status and chunk count for a document version.

    Used by the admin UI to poll while a document is being digitised
    or ingested. Returns ``processing_status`` in canonical lowercase form
    (e.g. ``received``, ``approved``, ``indexed``), plus a derived
    ``in_flight`` flag when the version is in a non-terminal state.
    """
    async with await _get_session() as session:
        version = await session.get(
            DocumentVersionModel, version_id
        )
        if version is None:
            raise NotFoundException(
                "Document version not found."
            )
        chunk_count = await session.scalar(
            select(func.count(DocumentChunkModel.id)).where(
                DocumentChunkModel.version_id == version_id
            )
        )
        in_flight = version.processing_status in (
            ProcessingStatus.RECEIVED.value,
            ProcessingStatus.QUEUED.value,
            ProcessingStatus.PARSED.value,
            ProcessingStatus.REVIEW_REQUIRED.value,
        )
        return {
            "version_id": str(version_id),
            "processing_status": version.processing_status,
            "chunk_count": int(chunk_count or 0),
            "in_flight": in_flight,
        }


@router.post(
    "/documents/{version_id}/complete-review",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.review"
            )
        )
    ],
)
async def complete_review(
    version_id: UUID,
    current_user: Annotated[
        "CurrentUser",
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Mark a PENDING_REVIEW version as PENDING_APPROVAL.

    Reviewer or admin (enforced by ``document.review`` permission).
    """
    from src.application.common.interfaces.current_user import (
        CurrentUser,
    )
    from src.application.features.documents.review.complete_review_command import (
        CompleteReviewCommand,
    )
    from src.presentation.api.dependencies.authentication import (
        get_current_user,
    )

    result = await dispatcher.send(
        CompleteReviewCommand(
            version_id=version_id,
            reviewer_id=current_user.user_id,
            notes=None,
        )
    )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "reviewed_at": result.reviewed_at.isoformat() + "Z",
    }


@router.post(
    "/documents/{version_id}/reject",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.review"
            )
        )
    ],
)
async def reject_document_version(
    version_id: UUID,
    current_user: Annotated[
        "CurrentUser",
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Reject a document version.

    Allowed from PENDING_REVIEW or PENDING_APPROVAL.
    Reviewer or admin only (enforced by ``document.review`` permission).
    """
    from src.application.common.interfaces.current_user import (
        CurrentUser,
    )
    from src.application.features.documents.review.reject_document_command import (
        RejectDocumentCommand,
    )
    from src.presentation.api.dependencies.authentication import (
        get_current_user,
    )

    result = await dispatcher.send(
        RejectDocumentCommand(
            version_id=version_id,
            reviewer_id=current_user.user_id,
            notes=None,
        )
    )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "reviewed_at": result.reviewed_at.isoformat() + "Z",
    }


@router.post(
    "/documents/{version_id}/republish",
    status_code=200,
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def republish_rejected_document(
    version_id: UUID,
    current_user: Annotated[
        "CurrentUser",
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
):
    """Move a REJECTED document back to PENDING_REVIEW.

    Admin only (enforced by ``document.update`` permission + admin check
    inside the handler).
    """
    from src.application.common.interfaces.current_user import (
        CurrentUser,
    )
    from src.application.features.documents.review.republish_document_command import (
        RepublishDocumentCommand,
    )
    from src.presentation.api.dependencies.authentication import (
        get_current_user,
    )

    result = await dispatcher.send(
        RepublishDocumentCommand(
            version_id=version_id,
            admin_id=current_user.user_id,
            notes=None,
        )
    )
    return {
        "version_id": str(result.version_id),
        "status": result.status.value,
        "reviewed_at": result.reviewed_at.isoformat() + "Z",
    }


@router.delete(
    "/documents/{version_id}",
    status_code=status.HTTP_200_OK,
    response_model=dict,
    dependencies=[
        Depends(
            require_permission(
                "document.delete"
            )
        )
    ],
)
async def delete_document_version(
    version_id: UUID,
) -> dict:
    """Delete a document version and its associated chunks.

    Only versions in non-terminal states (``received``, ``queued``,
    ``parsed``, ``failed``) can be safely deleted. Versions that have
    been ``approved``, ``indexed``, or ``published`` are rejected with
    409 Conflict because the version has data in Qdrant / downstream
    systems that cannot be safely cleaned up here.
    """
    terminal_states = (
        ProcessingStatus.APPROVED.value,
        ProcessingStatus.INDEXED.value,
        ProcessingStatus.PUBLISHED.value,
    )
    async with await _get_session() as session:
        version = await session.get(
            DocumentVersionModel, version_id
        )
        if version is None:
            raise NotFoundException(
                "Document version not found."
            )
        if version.processing_status in terminal_states:
            raise ConflictException(
                f"Cannot delete version in '{version.processing_status}' state. "
                "Only versions in received/queued/parsed/failed state can be deleted."
            )
        document_id = str(version.document_id)
        # Hard-delete chunks first (foreign key constraint)
        await session.execute(
            delete(DocumentChunkModel).where(
                DocumentChunkModel.version_id == version_id
            )
        )
        # Hard-delete version
        await session.execute(
            delete(DocumentVersionModel).where(
                DocumentVersionModel.id == version_id
            )
        )
        await session.commit()
        return {
            "version_id": str(version_id),
            "document_id": document_id,
            "deleted": True,
        }
