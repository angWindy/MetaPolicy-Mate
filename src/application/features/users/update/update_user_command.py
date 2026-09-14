from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class UpdateUserCommand:
    user_id: UUID

    email: str
    full_name: str

    department_id: UUID | None

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.UPDATE

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
            "operation":
                "user_updated",

            "user_id":
                self.user_id,

            "email":
                self.email
                .strip()
                .lower(),

            "full_name":
                self.full_name.strip(),

            "department_id":
                (
                    str(
                        self.department_id
                    )
                    if self.department_id
                    else None
                ),
        }