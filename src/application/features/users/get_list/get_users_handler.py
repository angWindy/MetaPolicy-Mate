from dataclasses import dataclass

from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.users.common.user_item import (
    UserItem,
)
from src.application.features.users.get_list.get_users_query import (
    GetUsersQuery,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


@dataclass(frozen=True)
class GetUsersResult:
    items: list[
        UserItem
    ]

    total: int
    page: int
    page_size: int


class GetUsersHandler(
    RequestHandler[
        GetUsersQuery,
        GetUsersResult,
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
        request: GetUsersQuery,
    ) -> GetUsersResult:
        skip = (
            request.page - 1
        ) * request.page_size

        users = (
            await self
            ._user_repository
            .get_list(
                search=request.search,
                is_active=(
                    request.is_active
                ),
                skip=skip,
                limit=(
                    request.page_size
                ),
            )
        )

        total = (
            await self
            ._user_repository
            .count(
                search=request.search,
                is_active=(
                    request.is_active
                ),
            )
        )

        return GetUsersResult(
            items=[
                UserItem.from_entity(
                    user
                )
                for user in users
            ],

            total=total,

            page=request.page,

            page_size=(
                request.page_size
            ),
        )