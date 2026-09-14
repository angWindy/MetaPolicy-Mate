from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.users.delete.delete_user_command import (
    DeleteUserCommand,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class DeleteUserHandler(
    RequestHandler[
        DeleteUserCommand,
        None,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
    ) -> None:
        self._user_repository = user_repository

    async def handle(
        self,
        request: DeleteUserCommand,
    ) -> None:
        user = await self._user_repository.get_by_id(
            request.user_id
        )

        if user is None:
            raise NotFoundException(
                f"User with id {request.user_id} not found."
            )

        await self._user_repository.delete(request.user_id)
