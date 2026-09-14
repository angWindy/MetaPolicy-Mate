from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class GetActivityLogsQuery:
    user_id: UUID | None

    request_name: str | None
    status: str | None

    from_at: datetime | None
    to_at: datetime | None

    page: int
    page_size: int