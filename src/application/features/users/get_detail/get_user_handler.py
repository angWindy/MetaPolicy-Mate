from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.users.common.user_item import (
    UserItem,
)
from src.application.features.users.get_detail.get_user_query import (
    GetUserQuery,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class GetUserHandler(
    RequestHandler[
        GetUserQuery,
        UserItem,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
    ) -> None:
        self._user_repository = (
            user_repository
        )

    async def handle(
        self,
        request: GetUserQuery,
    ) -> UserItem:
        user = (
            await self
            ._user_repository
            .get_by_id(
                request.user_id
            )
        )

        if user is None:
            raise NotFoundException(
                "User not found."
            )

        return UserItem.from_entity(
            user
        )