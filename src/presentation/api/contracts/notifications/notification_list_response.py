from pydantic import BaseModel

from src.presentation.api.contracts.notifications.notification_response import (
    NotificationResponse,
)


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int
