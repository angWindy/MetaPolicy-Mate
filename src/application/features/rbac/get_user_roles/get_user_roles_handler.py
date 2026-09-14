from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.roles.common.role_item import (
    RoleItem,
)
from src.application.features.rbac.get_user_roles.get_user_roles_query import (
    GetUserRolesQuery,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class GetUserRolesHandler(
    RequestHandler[
        GetUserRolesQuery,
        list[RoleItem],
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        role_repository: RoleRepository,
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._role_repository = (
            role_repository
        )

    async def handle(
        self,
        request: GetUserRolesQuery,
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