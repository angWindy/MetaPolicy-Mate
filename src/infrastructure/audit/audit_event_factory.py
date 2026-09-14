from uuid import UUID

from src.application.common.interfaces.audit_event_factory import (
    AuditEventFactory as AuditEventFactoryProtocol,
)
from src.application.common.interfaces.request_context import RequestContext
from src.domain.audit.audit_actor import AuditActor
from src.domain.audit.audit_context import AuditContext
from src.domain.audit.audit_data import AuditData
from src.domain.audit.audit_event import AuditEvent
from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_actor_type import AuditActorType
from src.domain.enums.audit_entity import AuditEntity


class AuditEventFactory(AuditEventFactoryProtocol):
    def __init__(
        self,
        context: RequestContext,
    ) -> None:
        self._context = context

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
        return AuditEvent(
            school_id=school_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            actor=AuditActor(
                id=actor_id or self._context.user_id,
                type=actor_type,
            ),
            context=AuditContext(
                ip=self._context.ip_address,
                user_agent=self._context.user_agent,
                device_id=self._context.device_id,
                trace_id=self._context.trace_id,
            ),
            data=AuditData(
                before=before,
                after=after,
                extra=extra,
            ),
        )