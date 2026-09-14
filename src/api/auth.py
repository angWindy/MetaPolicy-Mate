from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.rag.config import RAGSettings, get_rag_settings
from src.security.policy import AuthenticatedIdentity


PUBLIC_PATHS = {"/health", "/api/v1/status", "/docs", "/openapi.json", "/redoc"}


def _identity_from_headers(request: Request) -> AuthenticatedIdentity | None:
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None
    tenant_id = request.headers.get("X-Tenant-Id") or "hust"
    department = request.headers.get("X-Department") or "TCCB"
    roles_header = request.headers.get("X-Roles") or ""
    assigned_roles = frozenset(
        role.strip().lower()
        for role in roles_header.split(",")
        if role.strip()
    )
    clearance = request.headers.get("X-Clearance")
    granted_clearance = None
    if clearance:
        from src.domain.schemas import ClassificationLevel

        try:
            granted_clearance = ClassificationLevel(clearance)
        except ValueError:
            granted_clearance = None
    return AuthenticatedIdentity(
        user_id=user_id,
        tenant_id=tenant_id,
        department=department,
        assigned_roles=assigned_roles,
        granted_clearance=granted_clearance,
        is_authenticated=True,
    )


class DevBypassAuthMiddleware(BaseHTTPMiddleware):
    """Trust dev/test headers as identity, but never bypass in production."""

    def __init__(
        self,
        app,
        *,
        settings: RAGSettings | None = None,
    ) -> None:
        super().__init__(app)
        self.settings = settings or get_rag_settings()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        identity = _identity_from_headers(request)
        if self.settings.app_env == "production":
            if identity is not None:
                # Production must never accept dev-bypass headers.
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=401,
                    detail="Dev bypass headers are forbidden in production.",
                )
        elif self.settings.dev_auth_bypass and identity is not None:
            request.state.authenticated_identity = identity
        return await call_next(request)