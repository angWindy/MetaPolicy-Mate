from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class UpdateUserStatusCommand:
    user_id: UUID
    is_active: bool

    @property
    def action(
        self,
    ) -> AuditAction:
        if self.is_active:
            return AuditAction.RESTORE

        return (
            AuditAction.DISABLE_USER
        )

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return AuditEntity.SCHOOL_USER

    @property
    def entity_id(
        self,
    ) -> UUID:
        return self.user_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "user_enabled"
                if self.is_active
                else "user_disabled"
            ),

            "user_id":
                self.user_id,

            "is_active":
                self.is_active,
        }