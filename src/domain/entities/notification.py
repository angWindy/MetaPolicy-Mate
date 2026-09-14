from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.schemas import NotificationType


@dataclass
class Notification:
    id: UUID
    user_id: UUID
    type: NotificationType
    title: str
    body: str | None
    related_document_id: UUID | None
    is_read: bool
    created_at: datetime
