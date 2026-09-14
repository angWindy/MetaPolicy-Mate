from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.document_section_metadata.approve.approve_section_metadata_command import (
    ApproveSectionMetadataCommand,
)
from src.application.features.document_section_metadata.extract.extract_section_metadata_command import (
    ExtractSectionMetadataCommand,
)
from src.application.features.document_section_metadata.get_pending.get_pending_section_metadata_query import (
    GetPendingSectionMetadataQuery,
)
from src.application.features.document_section_metadata.reject.reject_section_metadata_command import (
    RejectSectionMetadataCommand,
)
from src.presentation.api.contracts.document_section_metadata.approve_section_metadata_request import (
    ApproveSectionMetadataRequest,
)
from src.presentation.api.contracts.document_section_metadata.reject_section_metadata_request import (
    RejectSectionMetadataRequest,
)
from src.presentation.api.contracts.document_section_metadata.section_metadata_draft_response import (
    SectionMetadataDraftResponse,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)
from src.presentation.api.dependencies.document_access import (
    require_document_access,
    require_metadata_draft_document_access,
)


router = APIRouter()


def _to_response(
    item,
) -> SectionMetadataDraftResponse:
    return SectionMetadataDraftResponse(
        id=item.id,
        document_id=item.document_id,
        version_id=item.version_id,
        section_id=item.section_id,
        chunk_id=item.chunk_id,
        metadata=item.metadata,
        cross_references=(
            item.cross_references
        ),
        needs_human_review=(
            item.needs_human_review
        ),
        rationale=item.rationale,
        status=item.status,
        reviewed_by=item.reviewed_by,
        reviewed_at=item.reviewed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _require_user_id(
    current_user: CurrentUser,
) -> UUID:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Authentication required.",
        )

    return current_user.user_id


@router.post(
    "/documents/{document_id}/"
    "versions/{version_id}/extract",
    response_model=list[
        SectionMetadataDraftResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.process"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def extract_section_metadata(
    document_id: UUID,
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> list[
    SectionMetadataDraftResponse
]:
    result = await dispatcher.send(
        ExtractSectionMetadataCommand(
            document_id=document_id,
            version_id=version_id,
        )
    )

    return [
        _to_response(item)
        for item in result
    ]


@router.get(
    "/documents/{document_id}/"
    "versions/{version_id}/pending",
    response_model=list[
        SectionMetadataDraftResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_document_access
        ),
    ],
)
async def get_pending_section_metadata(
    document_id: UUID,
    version_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[
    SectionMetadataDraftResponse
]:
    result = await dispatcher.send(
        GetPendingSectionMetadataQuery(
            document_id=document_id,
            version_id=version_id,
        )
    )

    return [
        _to_response(item)
        for item in result
    ]


@router.put(
    "/drafts/{draft_id}/approve",
    response_model=(
        SectionMetadataDraftResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_metadata_draft_document_access
        ),
    ],
)
async def approve_section_metadata(
    draft_id: UUID,
    request: (
        ApproveSectionMetadataRequest
    ),
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> SectionMetadataDraftResponse:
    reviewer_user_id = (
        _require_user_id(
            current_user
        )
    )

    result = await dispatcher.send(
        ApproveSectionMetadataCommand(
            draft_id=draft_id,
            reviewer_user_id=(
                reviewer_user_id
            ),
            metadata=(
                request.metadata
            ),
            cross_references=(
                request.cross_references
            ),
        )
    )

    return _to_response(result)


@router.put(
    "/drafts/{draft_id}/reject",
    response_model=(
        SectionMetadataDraftResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_metadata_draft_document_access
        ),
    ],
)
async def reject_section_metadata(
    draft_id: UUID,
    request: (
        RejectSectionMetadataRequest
    ),
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> SectionMetadataDraftResponse:
    reviewer_user_id = (
        _require_user_id(
            current_user
        )
    )

    result = await dispatcher.send(
        RejectSectionMetadataCommand(
            draft_id=draft_id,
            reviewer_user_id=(
                reviewer_user_id
            ),
            reason=request.reason,
        )
    )

    return _to_response(result)