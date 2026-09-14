from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.activity_logs.get_detail.get_activity_log_detail_query import (
    GetActivityLogDetailQuery,
)
from src.application.features.activity_logs.get_list.get_activity_logs_query import (
    GetActivityLogsQuery,
)
from src.presentation.api.contracts.activity_logs.activity_log_list_response import (
    ActivityLogListResponse,
)
from src.presentation.api.contracts.activity_logs.activity_log_response import (
    ActivityLogResponse,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
)


router = APIRouter()


def _to_response(
    item,
) -> ActivityLogResponse:
    return ActivityLogResponse(
        id=item.id,
        school_id=item.school_id,
        user_id=item.user_id,
        request_name=(
            item.request_name
        ),
        status=item.status,
        trace_id=item.trace_id,
        ip_address=item.ip_address,
        device_id=item.device_id,
        user_agent=item.user_agent,
        error_message=(
            item.error_message
        ),
        started_at=item.started_at,
        completed_at=(
            item.completed_at
        ),
    )


@router.get(
    "",
    response_model=(
        ActivityLogListResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "activity_log.read"
            )
        )
    ],
)
async def get_activity_logs(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],

    user_id: Annotated[
        UUID | None,
        Query(),
    ] = None,

    request_name: Annotated[
        str | None,
        Query(
            max_length=255
        ),
    ] = None,

    status: Annotated[
        str | None,
        Query(
            max_length=30
        ),
    ] = None,

    from_at: Annotated[
        datetime | None,
        Query(),
    ] = None,

    to_at: Annotated[
        datetime | None,
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
) -> ActivityLogListResponse:
    result = await dispatcher.send(
        GetActivityLogsQuery(
            user_id=user_id,
            request_name=(
                request_name
            ),
            status=status,
            from_at=from_at,
            to_at=to_at,
            page=page,
            page_size=page_size,
        )
    )

    return ActivityLogListResponse(
        items=[
            _to_response(item)
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/{log_id}",
    response_model=(
        ActivityLogResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "activity_log.read"
            )
        )
    ],
)
async def get_activity_log_detail(
    log_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> ActivityLogResponse:
    result = await dispatcher.send(
        GetActivityLogDetailQuery(
            log_id=log_id
        )
    )

    return _to_response(result)