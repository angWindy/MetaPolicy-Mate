from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.rbac.common.permission_item import (
    PermissionItem,
)
from src.application.features.rbac.get_user_permissions.get_user_permissions_query import (
    GetUserPermissionsQuery,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class GetUserPermissionsHandler(
    RequestHandler[
        GetUserPermissionsQuery,
        list[PermissionItem],
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        permission_repository: (
            PermissionRepository
        ),
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._permission_repository = (
            permission_repository
        )

    async def handle(
        self,
        request: (
            GetUserPermissionsQuery
        ),
    ) -> list[PermissionItem]:
        user = await (
            self._user_repository
            .get_by_id(
                request.user_id
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        permissions = await (
            self._permission_repository
            .get_by_user_id(
                request.user_id
            )
        )

        return [
            PermissionItem.from_entity(
                item
            )
            for item in permissions
        ]