from typing import Protocol
from uuid import UUID

from src.domain.entities.user import (
    User,
)


class UserRepository(
    Protocol
):
    async def get_by_id(
        self,
        user_id: UUID,
    ) -> User | None:
        ...

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:
        ...

    async def get_list(
        self,
        search: str | None,
        is_active: bool | None,
        skip: int,
        limit: int,
    ) -> list[User]:
        ...

    async def count(
        self,
        search: str | None,
        is_active: bool | None,
    ) -> int:
        ...

    async def add(
        self,
        user: User,
    ) -> None:
        ...

    async def update(
        self,
        user: User,
    ) -> None:
        ...

    async def delete(
        self,
        user_id: UUID,
    ) -> None:
        ...