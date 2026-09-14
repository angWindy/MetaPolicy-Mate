from typing import Protocol
from uuid import UUID

from src.domain.audit.audit_event import AuditEvent
from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_actor_type import AuditActorType
from src.domain.enums.audit_entity import AuditEntity


class AuditEventFactory(Protocol):
    def create(
        self,
        school_id: UUID | None,
        action: AuditAction,
        entity: AuditEntity,
        entity_id: UUID | None,
        actor_id: UUID | None,
        actor_type: AuditActorType,
        before: object | None = None,
        after: object | None = None,
        extra: dict[str, object] | None = None,
    ) -> AuditEvent:
        ...