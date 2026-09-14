from typing import Protocol
from uuid import UUID


class AuthorizationService(Protocol):
    async def has_permission(
        self,
        user_id: UUID,
        permission_code: str,
    ) -> bool:
        ...