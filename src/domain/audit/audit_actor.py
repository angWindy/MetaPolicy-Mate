from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_actor_type import AuditActorType


@dataclass
class AuditActor:
    id: UUID | None = None
    type: AuditActorType = AuditActorType.SYSTEM