from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.user_activity_log import (
    UserActivityLog,
)


@dataclass(frozen=True)
class ActivityLogItem:
    id: UUID

    school_id: UUID | None
    user_id: UUID | None

    request_name: str
    status: str

    trace_id: str | None

    ip_address: str | None
    device_id: str | None
    user_agent: str | None

    error_message: str | None

    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_entity(
        cls,
        item: UserActivityLog,
    ) -> "ActivityLogItem":
        return cls(
            id=item.id,
            school_id=item.school_id,
            user_id=item.user_id,
            request_name=(
                item.request_name
            ),
            status=item.status,
            trace_id=item.trace_id,
            ip_address=item.ip_address,
            device_id=item.device_id,
            user_agent=item.user_agent,
            error_message=(
                item.error_message
            ),
            started_at=item.started_at,
            completed_at=(
                item.completed_at
            ),
        )