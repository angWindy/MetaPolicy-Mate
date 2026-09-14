from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ActivityLogResponse(
    BaseModel
):
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