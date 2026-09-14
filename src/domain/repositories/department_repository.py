from typing import Protocol
from uuid import UUID

from src.domain.entities.department import Department


class DepartmentRepository(Protocol):
    async def get_by_id(
        self,
        department_id: UUID,
    ) -> Department | None:
        ...

    async def get_by_code(
        self,
        code: str,
    ) -> Department | None:
        ...

    async def get_all(
        self,
    ) -> list[Department]:
        ...

    async def add(
        self,
        department: Department,
    ) -> None:
        ...

    async def update(
        self,
        department: Department,
    ) -> None:
        ...