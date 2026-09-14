from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class UpdateRolePermissionsCommand:

    actor_user_id: UUID

    role_id: UUID

    permission_ids: list[UUID]

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.UPDATE

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return AuditEntity.ROLE

    @property
    def entity_id(
        self,
    ) -> UUID:
        return self.role_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "role_permissions_updated"
            ),
            "role_id": (
                self.role_id
            ),
            "permission_ids": (
                self.permission_ids
            ),
        }