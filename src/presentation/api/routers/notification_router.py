from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.notifications.get_unread_count.get_unread_count_query import (
    GetUnreadCountQuery,
)
from src.application.features.notifications.list.list_notifications_query import (
    ListNotificationsQuery,
)
from src.application.features.notifications.mark_all_read.mark_all_read_command import (
    MarkAllNotificationsReadCommand,
)
from src.application.features.notifications.mark_read.mark_read_command import (
    MarkNotificationReadCommand,
)
from src.presentation.api.contracts.notifications.mark_all_read_response import (
    MarkAllReadResponse,
)
from src.presentation.api.contracts.notifications.mark_read_response import (
    MarkReadResponse,
)
from src.presentation.api.contracts.notifications.notification_list_response import (
    NotificationListResponse,
)
from src.presentation.api.contracts.notifications.notification_response import (
    NotificationResponse,
)
from src.presentation.api.contracts.notifications.unread_count_response import (
    UnreadCountResponse,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
)


router = APIRouter()


@router.get(
    "",
    response_model=NotificationListResponse,
)
async def list_notifications(
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
    unread_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> NotificationListResponse:
    result = await dispatcher.send(
        ListNotificationsQuery(
            user_id=current_user.user_id,
            unread_only=unread_only,
            page=page,
            page_size=page_size,
        )
    )
    return NotificationListResponse(
        items=[
            NotificationResponse(
                id=item.id,
                type=item.type,
                title=item.title,
                body=item.body,
                related_document_id=(
                    item.related_document_id
                ),
                is_read=item.is_read,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        unread_count=result.unread_count,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def get_unread_count(
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
) -> UnreadCountResponse:
    result = await dispatcher.send(
        GetUnreadCountQuery(
            user_id=current_user.user_id,
        )
    )
    return UnreadCountResponse(
        unread_count=result.unread_count,
    )


@router.post(
    "/{notification_id}/read",
    response_model=MarkReadResponse,
)
async def mark_notification_read(
    notification_id: str,
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
) -> MarkReadResponse:
    from uuid import UUID

    result = await dispatcher.send(
        MarkNotificationReadCommand(
            notification_id=UUID(notification_id),
            user_id=current_user.user_id,
        )
    )
    return MarkReadResponse(
        success=result.success,
        unread_count=result.unread_count,
    )


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
)
async def mark_all_read(
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(get_request_dispatcher),
    ],
) -> MarkAllReadResponse:
    result = await dispatcher.send(
        MarkAllNotificationsReadCommand(
            user_id=current_user.user_id,
        )
    )
    return MarkAllReadResponse(
        marked_count=result.marked_count,
    )
