from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class AuditLog:
    id: UUID

    school_id: UUID | None = None

    actor_id: UUID | None = None
    actor_type: str = ""

    action: str = ""
    entity: str = ""
    entity_id: UUID | None = None

    old_values: str | None = None
    new_values: str | None = None
    metadata: str | None = None

    ip_address: str | None = None
    device_id: str | None = None
    user_agent: str | None = None

    created_at: datetime | None = None