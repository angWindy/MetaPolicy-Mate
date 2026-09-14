from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class AuditOutbox:
    id: UUID
    event_type: str = "audit.event"
    payload: str = ""
    status: str = "Pending"
    retry_count: int = 0
    created_at: datetime = field(
        default_factory=lambda: datetime.min
    )
    processed_at: datetime | None = None
    error: str | None = None