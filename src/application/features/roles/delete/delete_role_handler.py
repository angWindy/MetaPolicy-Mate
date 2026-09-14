from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.roles.delete.delete_role_command import (
    DeleteRoleCommand,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)


class DeleteRoleHandler(
    RequestHandler[
        DeleteRoleCommand,
        None,
    ]
):
    def __init__(
        self,
        role_repository: RoleRepository,
    ) -> None:
        self._role_repository = role_repository

    async def handle(
        self,
        request: DeleteRoleCommand,
    ) -> None:
        role = await self._role_repository.get_by_id(
            request.role_id
        )

        if role is None:
            raise NotFoundException(
                f"Role with id {request.role_id} not found."
            )

        # System roles cannot be deleted (they are bootstrap
        # roles like ADMIN / USER that the application
        # depends on for permission gating).
        if role.is_system:
            raise ConflictException(
                "Không thể xóa vai trò hệ thống. "
                "Hãy bỏ gán vai trò khỏi người dùng trước."
            )

        await self._role_repository.delete(request.role_id)
