from datetime import (
    datetime,
    timezone,
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
from src.application.features.users.common.user_item import (
    UserItem,
)
from src.application.features.users.update_status.update_user_status_command import (
    UpdateUserStatusCommand,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class UpdateUserStatusHandler(
    RequestHandler[
        UpdateUserStatusCommand,
        UserItem,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        token_version_cache: (
            TokenVersionCache
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = (
            user_repository
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
            UpdateUserStatusCommand
        ),
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

        if (
            user.is_active
            == request.is_active
        ):
            return UserItem.from_entity(
                user
            )

        user.is_active = (
            request.is_active
        )

        # Vô hiệu hóa token cũ khi
        # trạng thái tài khoản thay đổi.
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

        return UserItem.from_entity(
            user
        )