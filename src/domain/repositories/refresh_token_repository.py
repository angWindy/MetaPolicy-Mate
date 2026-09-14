from typing import Protocol
from uuid import UUID

from src.domain.entities.refresh_token import RefreshToken


class RefreshTokenRepository(Protocol):
    async def get_by_id(
        self,
        refresh_token_id: UUID,
    ) -> RefreshToken | None:
        ...

    async def get_by_hash(
        self,
        token_hash: str,
    ) -> RefreshToken | None:
        ...

    async def get_by_hash_for_update(
        self,
        token_hash: str,
    ) -> RefreshToken | None:
        ...

    async def add(
        self,
        refresh_token: RefreshToken,
    ) -> None:
        ...

    async def update(
        self,
        refresh_token: RefreshToken,
    ) -> None:
        ...

    async def revoke_all_by_user_id(
        self,
        user_id: UUID,
    ) -> None:
        ...