from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.notifications.mark_all_read.mark_all_read_command import (
    MarkAllNotificationsReadCommand,
)
from src.application.features.notifications.mark_all_read.mark_all_read_result import (
    MarkAllNotificationsReadResult,
)
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)


class MarkAllNotificationsReadHandler(
    RequestHandler[
        MarkAllNotificationsReadCommand,
        MarkAllNotificationsReadResult,
    ]
):
    def __init__(
        self,
        notification_repository: NotificationRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._notification_repository = (
            notification_repository
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: MarkAllNotificationsReadCommand,
    ) -> MarkAllNotificationsReadResult:
        marked = await (
            self._notification_repository.mark_all_read(
                request.user_id
            )
        )
        await self._unit_of_work.save_changes()
        return MarkAllNotificationsReadResult(
            marked_count=marked,
        )
