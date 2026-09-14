from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.notifications.get_unread_count.get_unread_count_query import (
    GetUnreadCountQuery,
)
from src.application.features.notifications.get_unread_count.get_unread_count_result import (
    GetUnreadCountResult,
)
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)


class GetUnreadCountHandler(
    RequestHandler[
        GetUnreadCountQuery,
        GetUnreadCountResult,
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
        request: GetUnreadCountQuery,
    ) -> GetUnreadCountResult:
        count = await (
            self._notification_repository.count_unread(
                request.user_id
            )
        )
        return GetUnreadCountResult(unread_count=count)
