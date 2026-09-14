import asyncio
import os
import sys

from dotenv import load_dotenv
from redis.asyncio import Redis

from config import get_settings
from infrastructure.auth.token_version_validator import (
    TokenVersionValidator,
)
from infrastructure.cache.redis_token_version_cache import (
    RedisTokenVersionCache,
)
from persistence.tenant.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


load_dotenv()


class FailIfCalledUserRepository:
    async def get_by_id(
        self,
        user_id,
    ):
        raise RuntimeError(
            "Repository must not be called on cache HIT"
        )


async def main() -> None:
    settings = get_settings()

    redis_url = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0",
    )

    redis_client = Redis.from_url(
        redis_url
    )

    session_factory = TenantSessionFactory()

    session = session_factory.create(
        settings.database_url
    )

    try:
        # ------------------------------------------
        # 1. Verify Redis connection
        # ------------------------------------------

        pong = await redis_client.ping()

        print("REDIS")
        print("Ping:", pong)

        if not pong:
            raise RuntimeError(
                "Redis ping failed"
            )

        # ------------------------------------------
        # 2. Get real demo user from Neon
        # ------------------------------------------

        user_repository = SqlAlchemyUserRepository(
            session
        )

        user = await user_repository.get_by_email(
            "admin@p234.demo"
        )

        if user is None:
            raise RuntimeError(
                "Demo admin not found"
            )

        print()
        print("USER")
        print("ID:", user.id)
        print(
            "TokenVersion:",
            user.token_version,
        )

        # ------------------------------------------
        # 3. Prepare Redis cache
        # ------------------------------------------

        cache = RedisTokenVersionCache(
            redis_client
        )

        cache_key = (
            f"token-version:{user.id}"
        )

        # Ensure CACHE MISS
        await redis_client.delete(
            cache_key
        )

        cached_before = await cache.get(
            user.id
        )

        print()
        print("CACHE BEFORE")
        print("Value:", cached_before)

        if cached_before is not None:
            raise RuntimeError(
                "Cache should be empty"
            )

        # ------------------------------------------
        # 4. CACHE MISS
        #
        # Redis miss
        # -> UserRepository
        # -> Neon
        # -> cache.set(...)
        # -> True
        # ------------------------------------------

        validator = TokenVersionValidator(
            cache=cache,
            repository=user_repository,
        )

        valid = (
            await validator.validate_token_version(
                user.id,
                str(user.token_version),
            )
        )

        print()
        print("CACHE MISS TEST")
        print("Valid:", valid)

        if not valid:
            raise RuntimeError(
                "Cache miss validation failed"
            )

        cached_after = await cache.get(
            user.id
        )

        print(
            "Cached value:",
            cached_after,
        )

        if cached_after != str(
            user.token_version
        ):
            raise RuntimeError(
                "Token version was not cached"
            )

        # ------------------------------------------
        # 5. CACHE HIT
        #
        # Use repository which raises immediately.
        # If validation succeeds, validator did not
        # touch the database.
        # ------------------------------------------

        cache_hit_validator = (
            TokenVersionValidator(
                cache=cache,
                repository=(
                    FailIfCalledUserRepository()
                ),
            )
        )

        cache_hit_valid = (
            await cache_hit_validator
            .validate_token_version(
                user.id,
                str(user.token_version),
            )
        )

        print()
        print("CACHE HIT TEST")
        print(
            "Valid:",
            cache_hit_valid,
        )

        if not cache_hit_valid:
            raise RuntimeError(
                "Cache hit validation failed"
            )

        # ------------------------------------------
        # 6. Invalid token version
        # ------------------------------------------

        invalid = (
            await cache_hit_validator
            .validate_token_version(
                user.id,
                "999",
            )
        )

        print()
        print("INVALID VERSION TEST")
        print(
            "Valid:",
            invalid,
        )

        if invalid:
            raise RuntimeError(
                "Invalid token version was accepted"
            )

        # ------------------------------------------
        # 7. Check TTL
        # ------------------------------------------

        ttl = await redis_client.ttl(
            cache_key
        )

        print()
        print("CACHE TTL")
        print(
            "Seconds:",
            ttl,
        )

        if ttl <= 0:
            raise RuntimeError(
                "Redis key does not have TTL"
            )

        print()
        print(
            "TokenVersion integration test PASS"
        )

    finally:
        # Remove integration-test cache entry.
        try:
            if "cache_key" in locals():
                await redis_client.delete(
                    cache_key
                )
        finally:
            await session.close()
            await session_factory.dispose()
            await redis_client.aclose()


asyncio.run(main())