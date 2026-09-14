from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.notifications.list.list_notifications_query import (
    ListNotificationsQuery,
)
from src.application.features.notifications.list.list_notifications_result import (
    ListNotificationsResult,
    NotificationItem,
)
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)


class ListNotificationsHandler(
    RequestHandler[
        ListNotificationsQuery,
        ListNotificationsResult,
    ]
):
    def __init__(
        self,
        notification_repository: NotificationRepository,
    ) -> None:
        self._notification_repository = (
            notification_repository
        )

    async def handle(
        self,
        request: ListNotificationsQuery,
    ) -> ListNotificationsResult:
        items, total = await (
            self._notification_repository.list_by_user(
                user_id=request.user_id,
                unread_only=request.unread_only,
                page=request.page,
                page_size=request.page_size,
            )
        )
        unread_count = (
            await self._notification_repository
            .count_unread(request.user_id)
        )
        return ListNotificationsResult(
            items=[
                NotificationItem(
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
                for item in items
            ],
            total=total,
            unread_count=unread_count,
            page=request.page,
            page_size=request.page_size,
        )
