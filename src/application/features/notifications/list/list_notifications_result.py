from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.schemas import NotificationType


@dataclass(frozen=True)
class NotificationItem:
    id: UUID
    type: NotificationType
    title: str
    body: str | None
    related_document_id: UUID | None
    is_read: bool
    created_at: datetime


@dataclass(frozen=True)
class ListNotificationsResult:
    items: list[NotificationItem]
    total: int
    unread_count: int
    page: int
    page_size: int
