from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.notifications.mark_read.mark_read_command import (
    MarkNotificationReadCommand,
)
from src.application.features.notifications.mark_read.mark_read_result import (
    MarkNotificationReadResult,
)
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)


class MarkNotificationReadHandler(
    RequestHandler[
        MarkNotificationReadCommand,
        MarkNotificationReadResult,
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
        request: MarkNotificationReadCommand,
    ) -> MarkNotificationReadResult:
        marked = await (
            self._notification_repository.mark_read(
                notification_id=request.notification_id,
                user_id=request.user_id,
            )
        )
        if not marked:
            existing = await (
                self._notification_repository.get_by_id(
                    notification_id=request.notification_id,
                    user_id=request.user_id,
                )
            )
            if existing is None:
                raise NotFoundException(
                    "Notification not found."
                )
        await self._unit_of_work.save_changes()
        unread_count = await (
            self._notification_repository.count_unread(
                request.user_id
            )
        )
        return MarkNotificationReadResult(
            success=True,
            unread_count=unread_count,
        )
