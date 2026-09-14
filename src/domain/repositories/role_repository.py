from typing import Protocol
from uuid import UUID

from src.domain.entities.role import (
    Role,
)


class RoleRepository(
    Protocol
):
    async def get_by_id(
        self,
        role_id: UUID,
    ) -> Role | None:
        ...

    async def get_by_code(
        self,
        code: str,
    ) -> Role | None:
        ...

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Role]:
        ...

    async def get_all(
        self,
    ) -> list[Role]:
        ...

    async def add(
        self,
        role: Role,
    ) -> None:
        ...

    async def update(
        self,
        role: Role,
    ) -> None:
        ...

    async def replace_for_user(
        self,
        user_id: UUID,
        role_ids: list[UUID],
    ) -> None:
        ...

    async def delete(
        self,
        role_id: UUID,
    ) -> None:
        ...