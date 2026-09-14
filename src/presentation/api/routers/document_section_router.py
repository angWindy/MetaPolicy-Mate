from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.document_section_versions.create.create_document_section_version_command import (
    CreateDocumentSectionVersionCommand,
)
from src.application.features.document_section_versions.get_versions.get_document_section_versions_query import (
    GetDocumentSectionVersionsQuery,
)
from src.application.features.document_section_versions.update_effectiveness.update_section_version_effectiveness_command import (
    UpdateSectionVersionEffectivenessCommand,
)
from src.presentation.api.contracts.document_sections.create_document_section_version_request import (
    CreateDocumentSectionVersionRequest,
)
from src.presentation.api.contracts.document_sections.document_section_version_response import (
    DocumentSectionVersionResponse,
)
from src.presentation.api.contracts.document_sections.update_section_version_effectiveness_request import (
    UpdateSectionVersionEffectivenessRequest,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)
from src.presentation.api.dependencies.document_access import (
    require_section_document_access,
)

router = APIRouter()


def _to_response(
    item,
) -> DocumentSectionVersionResponse:
    return DocumentSectionVersionResponse(
        id=item.id,
        section_id=item.section_id,
        version_number=(
            item.version_number
        ),
        content=item.content,
        effective_from=(
            item.effective_from
        ),
        effective_to=(
            item.effective_to
        ),
        is_current=item.is_current,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get(
    "/{section_id}/versions",
    response_model=list[
        DocumentSectionVersionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_section_document_access
        ),
    ],
)
async def get_document_section_versions(
    section_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[
    DocumentSectionVersionResponse
]:
    result = await dispatcher.send(
        GetDocumentSectionVersionsQuery(
            section_id=section_id
        )
    )

    return [
        _to_response(item)
        for item in result
    ]


@router.post(
    "/{section_id}/versions",
    response_model=(
        DocumentSectionVersionResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_section_document_access
        ),
    ],
)
async def create_document_section_version(
    section_id: UUID,
    request: (
        CreateDocumentSectionVersionRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DocumentSectionVersionResponse:
    result = await dispatcher.send(
        CreateDocumentSectionVersionCommand(
            section_id=section_id,
            content=request.content,
            effective_from=(
                request.effective_from
            ),
            effective_to=(
                request.effective_to
            ),
            is_current=(
                request.is_current
            ),
        )
    )

    return _to_response(result)


@router.put(
    "/{section_id}/versions/"
    "{version_id}",
    response_model=(
        DocumentSectionVersionResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_section_document_access
        ),
    ],
)
async def update_section_version_effectiveness(
    section_id: UUID,
    version_id: UUID,
    request: (
        UpdateSectionVersionEffectivenessRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DocumentSectionVersionResponse:
    result = await dispatcher.send(
        UpdateSectionVersionEffectivenessCommand(
            section_id=section_id,
            version_id=version_id,
            effective_from=(
                request.effective_from
            ),
            effective_to=(
                request.effective_to
            ),
            is_current=(
                request.is_current
            ),
        )
    )

    return _to_response(result)