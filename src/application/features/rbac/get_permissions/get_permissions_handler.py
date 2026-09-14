from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.rbac.common.permission_item import (
    PermissionItem,
)
from src.application.features.rbac.get_permissions.get_permissions_query import (
    GetPermissionsQuery,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)


class GetPermissionsHandler(
    RequestHandler[
        GetPermissionsQuery,
        list[PermissionItem],
    ]
):
    def __init__(
        self,
        permission_repository: (
            PermissionRepository
        ),
    ) -> None:
        self._permission_repository = (
            permission_repository
        )

    async def handle(
        self,
        request: GetPermissionsQuery,
    ) -> list[PermissionItem]:
        permissions = await (
            self._permission_repository
            .get_all()
        )

        if request.module:
            module = (
                request.module
                .strip()
                .lower()
            )

            permissions = [
                item
                for item in permissions
                if (
                    item.module.lower()
                    == module
                )
            ]

        return [
            PermissionItem.from_entity(
                item
            )
            for item in permissions
        ]