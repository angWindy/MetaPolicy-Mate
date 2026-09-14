from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
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
from src.application.features.roles.create.create_role_command import (
    CreateRoleCommand,
)
from src.domain.entities.role import (
    Role,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class CreateRoleHandler(
    RequestHandler[
        CreateRoleCommand,
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
        request: CreateRoleCommand,
    ) -> RoleItem:
        code = (
            request.code
            .strip()
            .upper()
        )

        name = (
            request.name
            .strip()
        )

        description = (
            request.description.strip()
            if request.description
            else None
        )

        if not code:
            raise ConflictException(
                "Role code is required."
            )

        if not name:
            raise ConflictException(
                "Role name is required."
            )

        existing = await (
            self._role_repository
            .get_by_code(code)
        )

        if existing is not None:
            raise ConflictException(
                "Role code already exists."
            )

        role = Role(
            id=uuid4(),
            code=code,
            name=name,
            description=description,

            # Role tạo thủ công không phải
            # system role.
            is_system=False,

            created_at=datetime.now(
                timezone.utc
            ),
        )

        await (
            self._role_repository
            .add(role)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return RoleItem.from_entity(
            role
        )