from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetUnreadCountResult:
    unread_count: int
