from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.roles.common.role_item import (
    RoleItem,
)
from src.application.features.roles.get_list.get_roles_query import (
    GetRolesQuery,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class GetRolesHandler(
    RequestHandler[
        GetRolesQuery,
        list[RoleItem],
    ]
):
    def __init__(
        self,
        role_repository: RoleRepository,
    ) -> None:
        self._role_repository = (
            role_repository
        )

    async def handle(
        self,
        request: GetRolesQuery,
    ) -> list[RoleItem]:
        roles = await (
            self._role_repository
            .get_all()
        )

        return [
            RoleItem.from_entity(
                role
            )
            for role in roles
        ]