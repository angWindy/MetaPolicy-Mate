from typing import Protocol, runtime_checkable
from uuid import UUID

from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity


@runtime_checkable
class AuditableRequest(Protocol):
    @property
    def action(self) -> AuditAction:
        ...

    @property
    def entity(self) -> AuditEntity:
        ...

    @property
    def entity_id(self) -> UUID | None:
        ...