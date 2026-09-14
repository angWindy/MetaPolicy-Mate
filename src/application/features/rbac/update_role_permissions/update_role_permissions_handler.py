from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.rbac.common.permission_item import (
    PermissionItem,
)
from src.application.features.rbac.update_role_permissions.update_role_permissions_command import (
    UpdateRolePermissionsCommand,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class UpdateRolePermissionsHandler(
    RequestHandler[
        UpdateRolePermissionsCommand,
        list[PermissionItem],
    ]
):
    def __init__(
        self,
        role_repository: RoleRepository,
        permission_repository: (
            PermissionRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._role_repository = (
            role_repository
        )

        self._permission_repository = (
            permission_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            UpdateRolePermissionsCommand
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

        unique_ids = list(
            dict.fromkeys(
                request.permission_ids
            )
        )

        for permission_id in unique_ids:
            permission = await (
                self._permission_repository
                .get_by_id(
                    permission_id
                )
            )

            if permission is None:
                raise NotFoundException(
                    "Permission not found: "
                    f"{permission_id}"
                )

        actor_permissions = await (
            self._permission_repository
            .get_by_user_id(
                request.actor_user_id
            )
        )

        actor_permission_ids = {
            permission.id
            for permission
            in actor_permissions
        }

        requested_permission_ids = set(
            unique_ids
        )

        if not (
            requested_permission_ids
            .issubset(
                actor_permission_ids
            )
        ):
            raise ForbiddenException(
                "You cannot grant "
                "permissions that you "
                "do not have."
            )

        await (
            self._permission_repository
            .replace_for_role(
                role_id=(
                    request.role_id
                ),
                permission_ids=(
                    unique_ids
                ),
            )
        )

        await (
            self._unit_of_work
            .save_changes()
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