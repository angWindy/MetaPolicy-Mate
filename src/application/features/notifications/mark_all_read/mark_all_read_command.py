from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class MarkAllNotificationsReadCommand:
    user_id: UUID
