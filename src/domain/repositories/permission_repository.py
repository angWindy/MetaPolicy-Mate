from typing import Protocol
from uuid import UUID

from src.domain.entities.permission import (
    Permission,
)


class PermissionRepository(
    Protocol
):
    async def get_by_id(
        self,
        permission_id: UUID,
    ) -> Permission | None:
        ...

    async def get_by_code(
        self,
        code: str,
    ) -> Permission | None:
        ...

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[Permission]:
        ...

    async def get_by_role_id(
        self,
        role_id: UUID,
    ) -> list[Permission]:
        ...

    async def get_all(
        self,
    ) -> list[Permission]:
        ...

    async def add(
        self,
        permission: Permission,
    ) -> None:
        ...

    async def replace_for_role(
        self,
        role_id: UUID,
        permission_ids: list[UUID],
    ) -> None:
        ...