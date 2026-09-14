from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Query,
    Depends,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.static_thresholds.create.create_static_threshold_command import (
    CreateStaticThresholdCommand,
)
from src.application.features.static_thresholds.get_history.get_static_threshold_history_query import (
    GetStaticThresholdHistoryQuery,
)
from src.application.features.static_thresholds.get_verified.get_verified_static_thresholds_query import (
    GetVerifiedStaticThresholdsQuery,
)
from src.application.features.static_thresholds.verify.verify_static_threshold_command import (
    VerifyStaticThresholdCommand,
)
from src.presentation.api.contracts.static_thresholds.create_static_threshold_request import (
    CreateStaticThresholdRequest,
)
from src.presentation.api.contracts.static_thresholds.static_threshold_response import (
    StaticThresholdResponse,
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
    can_access_section,
    ensure_section_document_access,
    get_current_department_id,
    require_threshold_document_access,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)

router = APIRouter()


def _to_response(
    item,
) -> StaticThresholdResponse:
    return StaticThresholdResponse(
        id=item.id,
        threshold_key=item.threshold_key,
        version_number=(
            item.version_number
        ),
        name=item.name,
        operator=item.operator,
        value=item.value,
        unit=item.unit,
        condition_text=(
            item.condition_text
        ),
        section_id=item.section_id,
        scope_key=item.scope_key,
        section_version_id=(
            item.section_version_id
        ),
        status=item.status,
        is_current=item.is_current,
        verified_at=item.verified_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get(
    "",
    response_model=list[
        StaticThresholdResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        )
    ],
)
async def get_verified_thresholds(
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
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> list[
    StaticThresholdResponse
]:
    result = await dispatcher.send(
        GetVerifiedStaticThresholdsQuery()
    )

    visible_items = []

    for item in result:
        allowed = await (
            can_access_section(
                section_id=(
                    item.section_id
                ),
                department_id=(
                    department_id
                ),
                scope=scope,
            )
        )

        if allowed:
            visible_items.append(
                item
            )

    return [
        _to_response(item)
        for item in visible_items
    ]

@router.get(
    "/{threshold_key}/history",
    response_model=list[
        StaticThresholdResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        )
    ],
)
async def get_threshold_history(
    threshold_key: str,

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

    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],

    scope_key: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
        ),
    ],
) -> list[
    StaticThresholdResponse
]:
    result = await dispatcher.send(
        GetStaticThresholdHistoryQuery(
            threshold_key=(
                threshold_key
            ),
            scope_key=scope_key,
        )
    )

    visible_items = []

    for item in result:
        allowed = await (
            can_access_section(
                section_id=(
                    item.section_id
                ),
                department_id=(
                    department_id
                ),
                scope=scope,
            )
        )

        if allowed:
            visible_items.append(
                item
            )

    return [
        _to_response(item)
        for item in visible_items
    ]


@router.post(
    "",
    response_model=(
        StaticThresholdResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        )
    ],
)
async def create_static_threshold(
    request: CreateStaticThresholdRequest,

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
) -> StaticThresholdResponse:

    await ensure_section_document_access(
        section_id=request.section_id,
        department_id=department_id,
        scope=scope,
    )

    result = await dispatcher.send(
        CreateStaticThresholdCommand(
            threshold_key=(
                request.threshold_key
            ),
            name=request.name,
            operator=request.operator,
            value=request.value,
            unit=request.unit,
            condition_text=(
                request.condition_text
            ),
            section_id=request.section_id,
            scope_key=request.scope_key,
            section_version_id=(
                request.section_version_id
            ),
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{threshold_id}/verify",
    response_model=(
        StaticThresholdResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.approve"
            )
        ),
        Depends(
            require_threshold_document_access
        ),
    ],
)
async def verify_static_threshold(
    threshold_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    confirm_replacement: Annotated[
        bool,
        Query(),
    ] = False,
) -> StaticThresholdResponse:
    result = await dispatcher.send(
        VerifyStaticThresholdCommand(
            threshold_id=threshold_id,
            confirm_replacement=(
                confirm_replacement
            ),
        )
    )

    return _to_response(result)