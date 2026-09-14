from typing import Protocol
from uuid import UUID

from src.domain.entities.notification import Notification


class NotificationRepository(Protocol):
    async def add(
        self,
        notification: Notification,
    ) -> None:
        ...

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        unread_only: bool,
        page: int,
        page_size: int,
    ) -> tuple[list[Notification], int]:
        ...

    async def get_by_id(
        self,
        notification_id: UUID,
        user_id: UUID,
    ) -> Notification | None:
        ...

    async def mark_read(
        self,
        notification_id: UUID,
        user_id: UUID,
    ) -> bool:
        ...

    async def mark_all_read(
        self,
        user_id: UUID,
    ) -> int:
        """Returns number of notifications marked."""
        ...

    async def count_unread(
        self,
        user_id: UUID,
    ) -> int:
        ...
