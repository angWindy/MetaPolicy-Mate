from uuid import UUID

from redis.asyncio import Redis

from src.application.common.interfaces.token_version_cache import (
    TokenVersionCache,
)


class RedisTokenVersionCache(TokenVersionCache):
    def __init__(
        self,
        cache: Redis,
    ) -> None:
        self._cache = cache

    @staticmethod
    def _build_key(
        user_id: UUID,
    ) -> str:
        return f"token-version:{user_id}"

    async def get(
        self,
        user_id: UUID,
    ) -> str | None:
        value = await self._cache.get(
            self._build_key(user_id)
        )

        if value is None:
            return None

        if isinstance(value, bytes):
            return value.decode("utf-8")

        return str(value)

    async def set(
        self,
        user_id: UUID,
        token_version: int,
    ) -> None:
        await self._cache.set(
            self._build_key(user_id),
            str(token_version),
            ex=12 * 60 * 60,
        )