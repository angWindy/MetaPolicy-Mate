from typing import Annotated
from uuid import UUID

from fastapi import (
    Depends,
    HTTPException,
    Request,
    status,
)
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.interfaces.current_user_validator import (
    CurrentUserValidator,
)
from src.application.common.interfaces.jwt_token_service import (
    JwtTokenService,
)
from src.application.common.interfaces.request_context import (
    RequestContext as RequestContextProtocol,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.infrastructure.services.current_user_service import (
    CurrentUserService,
)
from src.infrastructure.services.request_context import (
    RequestContext,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


_bearer = HTTPBearer(
    auto_error=False
)


async def get_authenticated_claims(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    request: Request,
    scope: Annotated[
        ServiceContainer,
        Depends(get_request_scope),
    ],
) -> dict[str, object]:
    # Accept either ``Authorization: Bearer ...`` (preferred for JSON APIs)
    # or ``?access_token=...`` (fallback for browser PDF iframes that
    # cannot set custom headers). The query-string form is only consulted
    # when no Authorization header is present, so it never weakens the
    # normal API path.
    used_query_token = False
    if credentials is None:
        query_token = request.query_params.get(
            "access_token",
        )
        if query_token:
            credentials = (
                HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=query_token,
                )
            )
            used_query_token = True

    if credentials is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Authentication required.",
        )

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid authentication scheme.",
        )

    # B-P1-04: audit when a JWT is supplied via the query string
    # fallback. Tokens in URLs land in server access logs, browser
    # history, and referer headers leaking across origins, so the
    # fallback should always leave a trail that security review can
    # grep for. Only logs a short fingerprint (first/last 4 chars),
    # never the token itself.
    if used_query_token:
        import logging

        _logger = logging.getLogger(
            "p234.security.auth"
        )
        token = credentials.credentials
        masked = (
            f"{token[:4]}***{token[-4:]}"
            if len(token) > 8
            else "***"
        )
        _logger.warning(
            "JWT supplied via query string on %s "
            "(fingerprint=%s). Prefer Authorization "
            "header to keep tokens out of access logs.",
            request.url.path,
            masked,
        )

    jwt_service = scope.get_required(
        JwtTokenService
    )

    try:
        claims = (
            jwt_service.validate_access_token(
                credentials.credentials
            )
        )
    except Exception:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid access token.",
        )

    user_id_value = claims.get(
        "sub"
    )

    token_version = claims.get(
        "TokenVersion"
    )

    if (
        user_id_value is None
        or token_version is None
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid access token.",
        )

    try:
        user_id = UUID(
            str(user_id_value)
        )
    except (
        ValueError,
        TypeError,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid access token.",
        )

    validator = scope.get_required(
        CurrentUserValidator
    )

    valid_version = (
        await validator
        .validate_token_version(
            user_id,
            str(token_version),
        )
    )

    if not valid_version:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Access token is no longer valid.",
        )

    return claims


async def get_current_user(
    claims: Annotated[
        dict[str, object],
        Depends(get_authenticated_claims),
    ],
) -> CurrentUser:
    return CurrentUserService(
        claims=claims,
        is_authenticated=True,
    )


async def get_request_context(
    request: Request,
    claims: Annotated[
        dict[str, object],
        Depends(get_authenticated_claims),
    ],
) -> RequestContextProtocol:
    headers = dict(
        request.headers
    )

    client_ip = None

    if request.client is not None:
        client_ip = (
            request.client.host
        )

    trace_id = request.headers.get(
        "x-request-id"
    )

    return RequestContext(
        claims=claims,
        headers=headers,
        ip_address=client_ip,
        trace_id=trace_id,
    )