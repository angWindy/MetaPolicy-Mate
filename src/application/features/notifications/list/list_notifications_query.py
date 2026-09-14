from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ListNotificationsQuery:
    user_id: UUID
    unread_only: bool
    page: int
    page_size: int
