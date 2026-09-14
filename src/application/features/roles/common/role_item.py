from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.role import (
    Role,
)


@dataclass(frozen=True)
class RoleItem:
    id: UUID

    code: str
    name: str

    description: str | None

    is_system: bool

    created_at: datetime | None

    @staticmethod
    def from_entity(
        role: Role,
    ) -> "RoleItem":
        return RoleItem(
            id=role.id,
            code=role.code,
            name=role.name,
            description=(
                role.description
            ),
            is_system=(
                role.is_system
            ),
            created_at=(
                role.created_at
            ),
        )