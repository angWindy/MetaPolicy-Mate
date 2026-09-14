from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
)
from src.application.common.interfaces.refresh_token_service import (
    RefreshTokenService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.features.auth.logout.logout_command import (
    LogoutCommand,
)
from src.domain.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)

from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)

class LogoutHandler(
    RequestHandler[
        LogoutCommand,
        None,
    ]
):
    def __init__(
        self,
        refresh_token_repository: RefreshTokenRepository,
        refresh_token_service: RefreshTokenService,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._refresh_token_repository = (
            refresh_token_repository
        )
        self._refresh_token_service = (
            refresh_token_service
        )
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: LogoutCommand,
    ) -> None:
        if not request.refresh_token:
            raise UnauthorizedException(
                "Invalid refresh token."
            )

        token_hash = (
            self._refresh_token_service
            .hash_token(
                request.refresh_token
            )
        )

        stored_token = (
            await self._refresh_token_repository
            .get_by_hash(
                token_hash
            )
        )

        if stored_token is None:
            raise UnauthorizedException(
                "Invalid refresh token."
            )

        if stored_token.revoked_at is not None:
            raise UnauthorizedException(
                "Refresh token has been revoked."
            )

        stored_token.revoked_at = (
            datetime.now(
                timezone.utc
            )
        )

        await (
            self._refresh_token_repository.update(
                stored_token
            )
        )

        await self._unit_of_work.save_changes()