from dataclasses import dataclass
from uuid import UUID

from src.domain.entities.department import (
    Department,
)


@dataclass(frozen=True)
class DepartmentItem:
    id: UUID
    code: str
    name: str
    is_active: bool

    @staticmethod
    def from_entity(
        department: Department,
    ) -> "DepartmentItem":
        return DepartmentItem(
            id=department.id,
            code=department.code,
            name=department.name,
            is_active=(
                department.is_active
            ),
        )