from src.application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
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
from src.application.features.auth.logout_all.logout_all_command import (
    LogoutAllCommand,
)
from src.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class LogoutAllHandler(
    RequestHandler[
        LogoutAllCommand,
        None,
    ]
):
    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: (
            RefreshTokenRepository
        ),
        token_version_cache: (
            TokenVersionCache
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._user_repository = (
            user_repository
        )

        self._refresh_token_repository = (
            refresh_token_repository
        )

        self._token_version_cache = (
            token_version_cache
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: LogoutAllCommand,
    ) -> None:
        user = await (
            self._user_repository
            .get_by_id(
                request.user_id
            )
        )

        if user is None:
            raise UnauthorizedException(
                "User not found."
            )

        if not user.is_active:
            raise UnauthorizedException(
                "User is not active."
            )

        await (
            self._refresh_token_repository
            .revoke_all_by_user_id(
                user.id
            )
        )

        user.token_version += 1

        await (
            self._user_repository
            .update(
                user
            )
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