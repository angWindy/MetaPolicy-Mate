from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class UserActivityLog:
    id: UUID

    school_id: UUID | None
    user_id: UUID | None

    request_name: str
    status: str

    trace_id: str | None = None

    ip_address: str | None = None
    device_id: str | None = None
    user_agent: str | None = None

    error_message: str | None = None

    started_at: datetime | None = None
    completed_at: datetime | None = None