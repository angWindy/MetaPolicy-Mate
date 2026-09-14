from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.roles.common.role_item import (
    RoleItem,
)
from src.application.features.roles.get_detail.get_role_query import (
    GetRoleQuery,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class GetRoleHandler(
    RequestHandler[
        GetRoleQuery,
        RoleItem,
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
        request: GetRoleQuery,
    ) -> RoleItem:
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

        return RoleItem.from_entity(
            role
        )