from dataclasses import dataclass
from uuid import UUID

from src.domain.entities.permission import (
    Permission,
)


@dataclass(frozen=True)
class PermissionItem:
    id: UUID
    code: str
    name: str
    module: str
    description: str | None

    @staticmethod
    def from_entity(
        permission: Permission,
    ) -> "PermissionItem":
        return PermissionItem(
            id=permission.id,
            code=permission.code,
            name=permission.name,
            module=permission.module,
            description=(
                permission.description
            ),
        )