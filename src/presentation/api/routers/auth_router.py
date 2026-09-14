from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
)

from src.application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
)
from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.auth.login.login_command import (
    LoginCommand,
)
from src.application.features.auth.logout.logout_command import (
    LogoutCommand,
)
from src.application.features.auth.logout_all.logout_all_command import (
    LogoutAllCommand,
)
from src.application.features.auth.refresh.refresh_command import (
    RefreshCommand,
)
from src.application.features.auth.register.register_command import (
    RegisterCommand,
)
from src.presentation.api.contracts.auth.login_request import (
    LoginRequest,
)
from src.presentation.api.contracts.auth.login_response import (
    LoginResponse,
)
from src.presentation.api.contracts.auth.logout_request import (
    LogoutRequest,
)
from src.presentation.api.contracts.auth.refresh_request import (
    RefreshRequest,
)
from src.presentation.api.contracts.auth.refresh_response import (
    RefreshResponse,
)
from src.presentation.api.contracts.auth.register_request import (
    RegisterRequest,
)
from src.presentation.api.contracts.auth.register_response import (
    RegisterResponse,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
)
from src.presentation.api.dependencies.chat_rate_limit import (
    rate_limit_by_ip,
)

router = APIRouter()


@router.post(
    "/login",
    response_model=LoginResponse,
)
async def login(
    request: LoginRequest,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> LoginResponse:
    result = await dispatcher.send(
        LoginCommand(
            email=str(
                request.email
            ),
            password=(
                request.password
            ),
            device_id=(
                request.device_id
            ),
        )
    )

    return LoginResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_at=result.expires_at,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[
        Depends(
            rate_limit_by_ip(
                bucket="refresh",
                max_requests=30,
                window_seconds=60,
            )
        )
    ],
)
async def refresh(
    request: RefreshRequest,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> RefreshResponse:
    result = await dispatcher.send(
        RefreshCommand(
            refresh_token=(
                request.refresh_token
            ),
            device_id=(
                request.device_id
            ),
        )
    )

    return RefreshResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_at=result.expires_at,
    )


@router.post(
    "/logout",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
)
async def logout(
    request: LogoutRequest,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> Response:
    await dispatcher.send(
        LogoutCommand(
            refresh_token=(
                request.refresh_token
            ),
        )
    )

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )


@router.post(
    "/logout-all",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
)
async def logout_all(
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> Response:
    user_id = (
        current_user.user_id
    )

    if user_id is None:
        raise UnauthorizedException(
            "User is not authenticated."
        )

    await dispatcher.send(
        LogoutAllCommand(
            user_id=user_id
        )
    )

    return Response(
        status_code=(
            status.HTTP_204_NO_CONTENT
        )
    )


@router.post(
    "/register",
    status_code=(
        status.HTTP_403_FORBIDDEN
    ),
)
async def register_disabled() -> dict:
    """Registration is disabled.

    User accounts are created by Admin only (UC-G-01).
    This endpoint always returns 403 Forbidden.
    """
    from fastapi import HTTPException

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Đăng ký không được phép. Vui lòng liên hệ quản trị viên để tạo tài khoản.",
    )