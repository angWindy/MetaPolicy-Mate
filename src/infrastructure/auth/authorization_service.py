from uuid import UUID

from src.application.common.interfaces.authorization_service import (
    AuthorizationService as AuthorizationServiceProtocol,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)


class AuthorizationService(
    AuthorizationServiceProtocol
):
    def __init__(
        self,
        permission_repository: PermissionRepository,
    ) -> None:
        self._permission_repository = (
            permission_repository
        )

    async def has_permission(
        self,
        user_id: UUID,
        permission_code: str,
    ) -> bool:
        permissions = (
            await self._permission_repository
            .get_by_user_id(
                user_id
            )
        )

        return any(
            permission.code
            == permission_code
            for permission in permissions
        )