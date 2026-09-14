from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.schemas import NotificationType


class NotificationResponse(BaseModel):
    id: UUID
    type: NotificationType
    title: str
    body: str | None
    related_document_id: UUID | None
    is_read: bool
    created_at: datetime
