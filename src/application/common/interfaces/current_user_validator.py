from typing import Protocol
from uuid import UUID


class CurrentUserValidator(Protocol):
    async def validate_token_version(
        self,
        user_id: UUID,
        token_version: str,
    ) -> bool:
        ...