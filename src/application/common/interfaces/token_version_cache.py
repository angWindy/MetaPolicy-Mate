from typing import Protocol
from uuid import UUID


class TokenVersionCache(Protocol):
    async def get(
        self,
        user_id: UUID,
    ) -> str | None:
        ...

    async def set(
        self,
        user_id: UUID,
        token_version: int,
    ) -> None:
        ...