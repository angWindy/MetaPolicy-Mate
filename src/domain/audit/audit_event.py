from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.domain.audit.audit_actor import AuditActor
from src.domain.audit.audit_context import AuditContext
from src.domain.audit.audit_data import AuditData
from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity


@dataclass
class AuditEvent:
    action: AuditAction
    entity: AuditEntity

    event_id: UUID = field(
        default_factory=uuid4
    )

    school_id: UUID | None = None
    entity_id: UUID | None = None

    actor: AuditActor = field(
        default_factory=AuditActor
    )

    data: AuditData = field(
        default_factory=AuditData
    )

    context: AuditContext = field(
        default_factory=AuditContext
    )

    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )