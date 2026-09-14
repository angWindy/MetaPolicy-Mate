from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class CreateUserCommand:
    email: str
    password: str
    full_name: str
    department_id: UUID | None

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.CREATE_USER

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return AuditEntity.SCHOOL_USER

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
                "user_created",

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