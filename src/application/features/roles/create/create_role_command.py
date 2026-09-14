from dataclasses import dataclass

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class CreateRoleCommand:
    code: str
    name: str

    description: str | None = None

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.CREATE

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return AuditEntity.ROLE

    @property
    def entity_id(
        self,
    ):
        return None

    def get_payload(
        self,
    ) -> object:
        return {
            "operation":
                "role_created",

            "code":
                self.code
                .strip()
                .upper(),

            "name":
                self.name.strip(),

            "description":
                (
                    self.description.strip()
                    if self.description
                    else None
                ),
        }