"""Notification service - helper to create notifications.

Used by document workflow handlers when transitioning status, e.g.
when a document moves to PENDING_REVIEW or PENDING_APPROVAL.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from src.domain.entities.notification import Notification
from src.domain.repositories.notification_repository import (
    NotificationRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.domain.schemas import NotificationType


@dataclass
class NotificationTarget:
    user_id: UUID
    title: str
    body: str | None = None
    related_document_id: UUID | None = None


class UnitOfWorkPort(Protocol):
    async def save_changes(self) -> None:
        ...


class NotificationService:
    """Helper that creates notification rows tied to user/document events.

    This is a lightweight, side-effect-only service that does NOT raise on
    failure (creating a notification must not break the primary workflow).
    """

    def __init__(
        self,
        notification_repository: NotificationRepository,
        user_repository: UserRepository,
        unit_of_work: UnitOfWorkPort,
    ) -> None:
        self._notification_repository = (
            notification_repository
        )
        self._user_repository = user_repository
        self._unit_of_work = unit_of_work

    async def notify(
        self,
        *,
        type: NotificationType,
        targets: list[NotificationTarget],
    ) -> int:
        """Send a notification to multiple users.

        Returns the number of notifications created.
        """
        if not targets:
            return 0

        now = datetime.now(timezone.utc)
        created = 0

        for target in targets:
            # Skip if user does not exist (best-effort)
            user = await self._user_repository.get_by_id(
                target.user_id
            )
            if user is None:
                continue
            notification = Notification(
                id=uuid4(),
                user_id=target.user_id,
                type=type,
                title=target.title[:255],
                body=target.body,
                related_document_id=(
                    target.related_document_id
                ),
                is_read=False,
                created_at=now,
            )
            await self._notification_repository.add(
                notification
            )
            created += 1

        if created > 0:
            await self._unit_of_work.save_changes()
        return created
