from collections.abc import AsyncIterator

from redis.asyncio import Redis

from src.application.common.interfaces.current_user_validator import (
    CurrentUserValidator,
)
from src.application.common.interfaces.token_version_cache import (
    TokenVersionCache,
)
from src.config import get_settings
from src.infrastructure.auth.token_version_validator import (
    TokenVersionValidator,
)
from src.infrastructure.cache.redis_token_version_cache import (
    RedisTokenVersionCache,
)
from src.infrastructure.dependency_injection.composition_root import (
    get_root_container,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.persistence.tenant.dependency_injection import (
    add_tenant_persistence,
)
from src.persistence.tenant.session_factory import (
    TenantSessionFactory,
)

from src.application.common.interfaces.authorization_service import (
    AuthorizationService,
)
from src.infrastructure.auth.authorization_service import (
    AuthorizationService as AuthorizationServiceImplementation,
)
from src.application.common.interfaces.chat_rate_limiter import (
    ChatRateLimiter,
)
from src.infrastructure.cache.redis_chat_rate_limiter import (
    RedisChatRateLimiter,
)

_session_factory = TenantSessionFactory()


def get_tenant_session_factory(
) -> TenantSessionFactory:
    return _session_factory


async def get_request_scope() -> AsyncIterator[
    ServiceContainer
]:
    settings = get_settings()

    session = _session_factory.create(
        settings.database_url
    )

    redis_client = Redis.from_url(
        settings.redis_url
    )

    scope = (
        get_root_container()
        .create_scope()
    )

    add_tenant_persistence(
        scope,
        session,
    )

    scope.register_scoped(
        AuthorizationService,
        AuthorizationServiceImplementation,
    )

    scope.register_instance(
        Redis,
        redis_client,
    )

    scope.register_scoped(
        ChatRateLimiter,
        RedisChatRateLimiter,
    )

    scope.register_scoped(
        TokenVersionCache,
        RedisTokenVersionCache,
    )

    scope.register_scoped(
        CurrentUserValidator,
        TokenVersionValidator,
    )

    # Register VectorStore so handlers that need to delete chunks
    # (e.g. DeleteRegulatoryDocumentHandler) can resolve it from the
    # request scope. The runtime is built lazily and cached at module
    # level by ``get_p234_rag_runtime``.
    from src.infrastructure.ai.rag_runtime import (
        get_p234_rag_runtime,
    )
    from src.retrieval.vector_store import (
        VectorStore,
    )

    scope.register_instance(
        VectorStore,
        get_p234_rag_runtime().vector_store,
    )

    try:
        yield scope

    finally:
        await session.close()
        await redis_client.aclose()