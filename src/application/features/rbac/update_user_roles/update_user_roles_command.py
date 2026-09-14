from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class UpdateUserRolesCommand:

    actor_user_id: UUID

    user_id: UUID

    role_ids: list[UUID]

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.UPDATE

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return (
            AuditEntity
            .SCHOOL_USER
        )

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
                "user_roles_updated"
            ),
            "user_id": (
                self.user_id
            ),
            "role_ids": (
                self.role_ids
            ),
        }