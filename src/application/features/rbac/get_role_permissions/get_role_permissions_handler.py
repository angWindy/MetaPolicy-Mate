from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.rbac.common.permission_item import (
    PermissionItem,
)
from src.application.features.rbac.get_role_permissions.get_role_permissions_query import (
    GetRolePermissionsQuery,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class GetRolePermissionsHandler(
    RequestHandler[
        GetRolePermissionsQuery,
        list[PermissionItem],
    ]
):
    def __init__(
        self,
        role_repository: RoleRepository,
        permission_repository: (
            PermissionRepository
        ),
    ) -> None:
        self._role_repository = (
            role_repository
        )

        self._permission_repository = (
            permission_repository
        )

    async def handle(
        self,
        request: (
            GetRolePermissionsQuery
        ),
    ) -> list[PermissionItem]:
        role = await (
            self._role_repository
            .get_by_id(
                request.role_id
            )
        )

        if role is None:
            raise NotFoundException(
                "Role not found."
            )

        permissions = await (
            self._permission_repository
            .get_by_role_id(
                request.role_id
            )
        )

        return [
            PermissionItem.from_entity(
                item
            )
            for item in permissions
        ]