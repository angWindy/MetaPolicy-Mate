from uuid import UUID

from src.application.common.interfaces.current_user_validator import (
    CurrentUserValidator,
)
from src.application.common.interfaces.token_version_cache import (
    TokenVersionCache,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)


class TokenVersionValidator(
    CurrentUserValidator
):
    def __init__(
        self,
        cache: TokenVersionCache,
        repository: UserRepository,
    ) -> None:
        self._cache = cache
        self._repository = repository

    async def validate_token_version(
        self,
        user_id: UUID,
        token_version: str,
    ) -> bool:
        # Cache có thể stale nếu DB commit
        # thành công nhưng Redis update lỗi.
        #
        # Vì vậy cache không được là nguồn
        # quyết định cuối cùng.
        try:
            cached_version = await (
                self._cache.get(user_id)
            )
        except Exception:
            cached_version = None

        user = await (
            self._repository.get_by_id(
                user_id
            )
        )

        if user is None:
            return False

        database_version = str(
            user.token_version
        )

        # Đồng bộ lại cache theo DB,
        # nhưng Redis lỗi không được làm
        # authentication fail nếu DB vẫn
        # truy cập được.
        if (
            cached_version
            != database_version
        ):
            try:
                await self._cache.set(
                    user.id,
                    user.token_version,
                )
            except Exception:
                pass

        return (
            database_version
            == token_version
        )