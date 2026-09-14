from uuid import (
    UUID,
    uuid4,
)

from redis.asyncio import Redis

from src.application.common.interfaces.chat_rate_limiter import (
    ChatRateLimiter,
)
from src.config import Settings


class RedisChatRateLimiter(
    ChatRateLimiter
):
    LOCK_SECONDS = 180

    _RELEASE_SCRIPT = """
    if redis.call(
        'get',
        KEYS[1]
    ) == ARGV[1] then
        return redis.call(
            'del',
            KEYS[1]
        )
    else
        return 0
    end
    """

    _INCREMENT_SCRIPT = """
    local current = redis.call(
        'incr',
        KEYS[1]
    )
    if current == 1 then
        redis.call(
            'expire',
            KEYS[1],
            ARGV[1]
        )
    end
    local ttl = redis.call(
        'ttl',
        KEYS[1]
    )
    return {current, ttl}
    """

    def __init__(
        self,
        redis: Redis,
        settings: Settings,
    ) -> None:
        self._redis = redis

        self._max_requests = (
            settings
            .chat_rate_limit_requests
        )

        self._window_seconds = (
            settings
            .chat_rate_limit_window_seconds
        )

    async def check(
        self,
        user_id: UUID,
    ) -> tuple[
        bool,
        int,
    ]:
        key = (
            f"chat-rate:"
            f"{user_id}"
        )

        return await self.check_key(
            key=key,
            max_requests=(
                self._max_requests
            ),
            window_seconds=(
                self._window_seconds
            ),
        )

    async def check_key(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[
        bool,
        int,
    ]:
        count, ttl = await self._redis.eval(
            self._INCREMENT_SCRIPT,
            1,
            key,
            window_seconds,
        )

        count = int(count)
        ttl = int(ttl)

        if count > max_requests:
            return (
                False,
                max(
                    ttl,
                    1,
                ),
            )

        return (
            True,
            0,
        )

    async def acquire_lock(
        self,
        user_id: UUID,
    ) -> str | None:
        key = (
            f"chat-running:"
            f"{user_id}"
        )

        token = uuid4().hex

        acquired = await self._redis.set(
            key,
            token,
            nx=True,
            ex=self.LOCK_SECONDS,
        )

        if not acquired:
            return None

        return token

    async def release_lock(
        self,
        user_id: UUID,
        token: str,
    ) -> None:
        key = (
            f"chat-running:"
            f"{user_id}"
        )

        await self._redis.eval(
            self._RELEASE_SCRIPT,
            1,
            key,
            token,
        )