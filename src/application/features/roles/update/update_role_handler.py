from src.application.common.exceptions.conflict_exception import (
    ConflictException,
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
from src.application.features.roles.common.role_item import (
    RoleItem,
)
from src.application.features.roles.update.update_role_command import (
    UpdateRoleCommand,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class UpdateRoleHandler(
    RequestHandler[
        UpdateRoleCommand,
        RoleItem,
    ]
):
    def __init__(
        self,
        role_repository: RoleRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._role_repository = (
            role_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: UpdateRoleCommand,
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

        name = (
            request.name.strip()
        )

        description = (
            request.description.strip()
            if request.description
            else None
        )

        if not name:
            raise ConflictException(
                "Role name is required."
            )

        role.name = name

        role.description = (
            description
        )

        await (
            self._role_repository
            .update(role)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return RoleItem.from_entity(
            role
        )