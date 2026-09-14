from collections.abc import Callable
from typing import Annotated

from fastapi import (
    Depends,
    HTTPException,
    status,
)

from src.application.common.interfaces.authorization_service import (
    AuthorizationService,
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


def require_permission(
    permission_code: str,
) -> Callable:
    async def dependency(
        current_user: Annotated[
            CurrentUser,
            Depends(get_current_user),
        ],
        scope: Annotated[
            ServiceContainer,
            Depends(get_request_scope),
        ],
    ) -> None:
        if current_user.user_id is None:
            raise HTTPException(
                status_code=(
                    status.HTTP_401_UNAUTHORIZED
                ),
                detail="Authentication required.",
            )

        authorization_service = (
            scope.get_required(
                AuthorizationService
            )
        )

        allowed = (
            await authorization_service
            .has_permission(
                current_user.user_id,
                permission_code,
            )
        )

        if not allowed:
            raise HTTPException(
                status_code=(
                    status.HTTP_403_FORBIDDEN
                ),
                detail="Permission denied.",
            )

    return dependency