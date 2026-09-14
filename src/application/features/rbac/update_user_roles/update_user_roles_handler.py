from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.token_version_cache import (
    TokenVersionCache,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.rbac.update_user_roles.update_user_roles_command import (
    UpdateUserRolesCommand,
)
from src.application.features.roles.common.role_item import (
    RoleItem,
)
from src.domain.repositories.permission_repository import (
    PermissionRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class UpdateUserRolesHandler(
    RequestHandler[
        UpdateUserRolesCommand,
        list[RoleItem],
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
        permission_repository: (
            PermissionRepository
        ),
        token_version_cache: (
            TokenVersionCache
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._role_repository = (
            role_repository
        )

        self._permission_repository = (
            permission_repository
        )

        self._token_version_cache = (
            token_version_cache
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            UpdateUserRolesCommand
        ),
    ) -> list[RoleItem]:
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

        unique_ids = list(
            dict.fromkeys(
                request.role_ids
            )
        )

        for role_id in unique_ids:
            role = await (
                self._role_repository
                .get_by_id(
                    role_id
                )
            )

            if role is None:
                raise NotFoundException(
                    "Role not found: "
                    f"{role_id}"
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

        for role_id in unique_ids:
            role_permissions = await (
                self._permission_repository
                .get_by_role_id(
                    role_id
                )
            )

            role_permission_ids = {
                permission.id
                for permission
                in role_permissions
            }

            if not (
                role_permission_ids
                .issubset(
                    actor_permission_ids
                )
            ):
                raise ForbiddenException(
                    "You cannot assign "
                    "a role containing "
                    "permissions that you "
                    "do not have."
                )

        current_roles = await (
            self._role_repository
            .get_by_user_id(
                request.user_id
            )
        )

        current_ids = {
            role.id
            for role in current_roles
        }

        requested_ids = set(
            unique_ids
        )

        # Nếu tập role không đổi thì
        # không tăng TokenVersion.
        if current_ids == requested_ids:
            return [
                RoleItem.from_entity(
                    role
                )
                for role
                in current_roles
            ]

        await (
            self._role_repository
            .replace_for_user(
                user_id=(
                    request.user_id
                ),
                role_ids=(
                    unique_ids
                ),
            )
        )

        user.token_version += 1

        user.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await (
            self._user_repository
            .update(user)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        await (
            self._token_version_cache
            .set(
                user.id,
                user.token_version,
            )
        )

        roles = await (
            self._role_repository
            .get_by_user_id(
                request.user_id
            )
        )

        return [
            RoleItem.from_entity(
                role
            )
            for role in roles
        ]