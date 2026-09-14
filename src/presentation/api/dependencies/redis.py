from collections.abc import AsyncIterator

from redis.asyncio import Redis

from src.config import get_settings


async def get_redis() -> AsyncIterator[Redis]:
    settings = get_settings()

    redis = Redis.from_url(
        settings.redis_url
    )

    try:
        yield redis
    finally:
        await redis.aclose()