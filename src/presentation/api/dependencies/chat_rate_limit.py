from collections.abc import (
    Awaitable,
    Callable,
)
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)

from src.application.common.interfaces.chat_rate_limiter import (
    ChatRateLimiter,
)
from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


RateLimitDependency = Callable[
    ...,
    Awaitable[
        None
    ],
]


def rate_limit_by_ip(
    *,
    bucket: str,
    max_requests: int,
    window_seconds: int,
) -> RateLimitDependency:
    async def dependency(
        request: Request,

        scope: Annotated[
            ServiceContainer,
            Depends(
                get_request_scope
            ),
        ],
    ) -> None:
        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        limiter = scope.get_required(
            ChatRateLimiter
        )

        allowed, retry_after = await (
            limiter.check_key(
                key=(
                    f"rate:{bucket}:"
                    f"{client_ip}"
                ),
                max_requests=(
                    max_requests
                ),
                window_seconds=(
                    window_seconds
                ),
            )
        )

        if allowed:
            return

        raise HTTPException(
            status_code=(
                status
                .HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many requests."
            ),
            headers={
                "Retry-After": str(
                    retry_after
                )
            },
        )

    return dependency


def rate_limit_by_user(
    *,
    bucket: str,
    max_requests: int,
    window_seconds: int,
) -> RateLimitDependency:
    async def dependency(
        current_user: Annotated[
            CurrentUser,
            Depends(
                get_current_user
            ),
        ],

        scope: Annotated[
            ServiceContainer,
            Depends(
                get_request_scope
            ),
        ],
    ) -> None:
        user_id = (
            current_user.user_id
        )

        if user_id is None:
            raise HTTPException(
                status_code=(
                    status
                    .HTTP_401_UNAUTHORIZED
                ),
                detail=(
                    "Authentication required."
                ),
            )

        limiter = scope.get_required(
            ChatRateLimiter
        )

        allowed, retry_after = await (
            limiter.check_key(
                key=(
                    f"rate:{bucket}:"
                    f"{user_id}"
                ),
                max_requests=(
                    max_requests
                ),
                window_seconds=(
                    window_seconds
                ),
            )
        )

        if allowed:
            return

        raise HTTPException(
            status_code=(
                status
                .HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many requests."
            ),
            headers={
                "Retry-After": str(
                    retry_after
                )
            },
        )

    return dependency