from typing import Annotated

from fastapi import Depends

from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.authentication import (
    get_request_context,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


async def get_request_dispatcher(
    scope: Annotated[
        ServiceContainer,
        Depends(get_request_scope),
    ],
) -> RequestDispatcher:
    """
    Dispatcher thông thường.

    Không yêu cầu authentication và không yêu cầu RequestContext.

    Dùng cho:
    - Login
    - Refresh
    - Logout
    - Các handler không phụ thuộc RequestContext
    """
    return scope.get_required(
        RequestDispatcher
    )


async def get_request_dispatcher_with_context(
    scope: Annotated[
        ServiceContainer,
        Depends(get_request_scope),
    ],
    request_context: Annotated[
        RequestContext,
        Depends(get_request_context),
    ],
) -> RequestDispatcher:
    """
    Dispatcher dành cho handler cần RequestContext.

    RequestContext được tạo từ JWT/HTTP request
    và bind vào ServiceContainer của request hiện tại.
    """
    scope.register_instance(
        RequestContext,
        request_context,
    )

    return scope.get_required(
        RequestDispatcher
    )