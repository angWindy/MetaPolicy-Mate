from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.document_effectiveness_alerts.create.create_document_effectiveness_alert_command import (
    CreateDocumentEffectivenessAlertCommand,
)
from src.application.features.document_effectiveness_alerts.due_documents.get_documents_due_for_effectiveness_query import (
    GetDocumentsDueForEffectivenessQuery,
)
from src.application.features.document_effectiveness_alerts.get_list.get_document_effectiveness_alerts_query import (
    GetDocumentEffectivenessAlertsQuery,
)
from src.application.features.document_effectiveness_alerts.update_status.update_document_effectiveness_alert_status_command import (
    UpdateDocumentEffectivenessAlertStatusCommand,
)

from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)

from src.presentation.api.contracts.document_effectiveness_alerts.create_document_effectiveness_alert_request import (
    CreateDocumentEffectivenessAlertRequest,
)
from src.presentation.api.contracts.document_effectiveness_alerts.document_effectiveness_alert_list_response import (
    DocumentEffectivenessAlertListResponse,
)
from src.presentation.api.contracts.document_effectiveness_alerts.document_effectiveness_alert_response import (
    DocumentEffectivenessAlertResponse,
)
from src.presentation.api.contracts.document_effectiveness_alerts.update_document_effectiveness_alert_status_request import (
    UpdateDocumentEffectivenessAlertStatusRequest,
)
from src.presentation.api.contracts.regulatory_documents.regulatory_document_response import (
    RegulatoryDocumentResponse,
)

from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.document_access import (
    ensure_document_access,
    get_current_department_id,
    require_alert_document_access,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


router = APIRouter()


def _to_response(
    item,
) -> DocumentEffectivenessAlertResponse:
    return DocumentEffectivenessAlertResponse(
        id=item.id,
        new_document_number=(
            item.new_document_number
        ),
        new_document_title=(
            item.new_document_title
        ),
        announced_date=(
            item.announced_date
        ),
        effective_date=(
            item.effective_date
        ),
        affected_document_id=(
            item.affected_document_id
        ),
        status=item.status,
        note=item.note,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
        effective_date_reached=(
            item.effective_date_reached
        ),
    )


@router.post(
    "",
    response_model=(
        DocumentEffectivenessAlertResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def create_alert(
    request: (
        CreateDocumentEffectivenessAlertRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],

    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> DocumentEffectivenessAlertResponse:
    await ensure_document_access(
        document_id=(
            request.affected_document_id
        ),
        department_id=department_id,
        scope=scope,
    )

    result = await dispatcher.send(
        CreateDocumentEffectivenessAlertCommand(
            new_document_number=(
                request.new_document_number
            ),
            new_document_title=(
                request.new_document_title
            ),
            announced_date=(
                request.announced_date
            ),
            effective_date=(
                request.effective_date
            ),
            affected_document_id=(
                request.affected_document_id
            ),
            note=request.note,
        )
    )

    return _to_response(
        result
    )


@router.get(
    "",
    response_model=(
        DocumentEffectivenessAlertListResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def get_alerts(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],

    # Dependency không có default phải
    # đứng trước alert_status/page/page_size.
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],

    alert_status: Annotated[
        DocumentEffectivenessAlertStatus
        | None,
        Query(),
    ] = None,

    page: Annotated[
        int,
        Query(
            ge=1
        ),
    ] = 1,

    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,
) -> (
    DocumentEffectivenessAlertListResponse
):
    result = await dispatcher.send(
        GetDocumentEffectivenessAlertsQuery(
            status=alert_status,
            page=page,
            page_size=page_size,
            department_id=(
                department_id
            ),
        )
    )

    return (
        DocumentEffectivenessAlertListResponse(
            items=[
                _to_response(item)
                for item
                in result.items
            ],
            total=result.total,
            page=result.page,
            page_size=(
                result.page_size
            ),
        )
    )


@router.put(
    "/{alert_id}/status",
    response_model=(
        DocumentEffectivenessAlertResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        ),
        Depends(
            require_alert_document_access
        ),
    ],
)
async def update_alert_status(
    alert_id: UUID,
    request: (
        UpdateDocumentEffectivenessAlertStatusRequest
    ),
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DocumentEffectivenessAlertResponse:
    result = await dispatcher.send(
        UpdateDocumentEffectivenessAlertStatusCommand(
            alert_id=alert_id,
            status=request.status,
        )
    )

    return _to_response(
        result
    )


@router.get(
    "/due-documents",
    response_model=list[
        RegulatoryDocumentResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.update"
            )
        )
    ],
)
async def get_documents_due_for_effectiveness(
    as_of: Annotated[
        date,
        Query(),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],
) -> list[
    RegulatoryDocumentResponse
]:
    result = await dispatcher.send(
        GetDocumentsDueForEffectivenessQuery(
            as_of=as_of,
            department_id=department_id,
        )
    )

    return [
        RegulatoryDocumentResponse(
            id=item.id,
            document_number=(
                item.document_number
            ),
            title=item.title,
            issued_by=item.issued_by,
            issued_date=item.issued_date,
            effective_date=(
                item.effective_date
            ),
            legal_status=(
                item.legal_status
            ),
            access_scope=(
                item.access_scope
            ),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in result
    ]