from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.users.create.create_user_command import (
    CreateUserCommand,
)
from src.application.features.users.delete.delete_user_command import (
    DeleteUserCommand,
)
from src.application.features.users.get_detail.get_user_query import (
    GetUserQuery,
)
from src.application.features.users.get_list.get_users_query import (
    GetUsersQuery,
)
from src.application.features.users.update.update_user_command import (
    UpdateUserCommand,
)
from src.application.features.users.update_status.update_user_status_command import (
    UpdateUserStatusCommand,
)

from src.presentation.api.contracts.users.create_user_request import (
    CreateUserRequest,
)
from src.presentation.api.contracts.users.update_user_request import (
    UpdateUserRequest,
)
from src.presentation.api.contracts.users.update_user_status_request import (
    UpdateUserStatusRequest,
)
from src.presentation.api.contracts.users.user_list_response import (
    UserListResponse,
)
from src.presentation.api.contracts.users.user_response import (
    UserResponse,
)

from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)


router = APIRouter()


def _to_response(
    item,
) -> UserResponse:
    return UserResponse(
        id=item.id,
        email=item.email,
        full_name=(
            item.full_name
        ),
        department_id=(
            item.department_id
        ),
        token_version=(
            item.token_version
        ),
        is_active=(
            item.is_active
        ),
        created_at=(
            item.created_at
        ),
        updated_at=(
            item.updated_at
        ),
    )


@router.get(
    "",
    response_model=UserListResponse,
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def get_users(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],

    search: Annotated[
        str | None,
        Query(
            max_length=255
        ),
    ] = None,

    is_active: Annotated[
        bool | None,
        Query(),
    ] = None,

    page: Annotated[
        int,
        Query(
            ge=1
        ),
    ] = 1,

    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,

) -> UserListResponse:
    result = await dispatcher.send(
        GetUsersQuery(
            search=search,
            is_active=is_active,
            page=page,
            page_size=page_size,
        )
    )

    return UserListResponse(
        items=[
            _to_response(item)
            for item
            in result.items
        ],

        total=result.total,

        page=result.page,

        page_size=result.page_size,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def get_user(
    user_id: UUID,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],

) -> UserResponse:
    result = await dispatcher.send(
        GetUserQuery(
            user_id=user_id
        )
    )

    return _to_response(
        result
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def create_user(
    request: CreateUserRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],

) -> UserResponse:
    result = await dispatcher.send(
        CreateUserCommand(
            email=request.email,
            password=(
                request.password
            ),
            full_name=(
                request.full_name
            ),
            department_id=(
                request.department_id
            ),
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],

) -> UserResponse:
    result = await dispatcher.send(
        UpdateUserCommand(
            user_id=user_id,
            email=request.email,
            full_name=(
                request.full_name
            ),
            department_id=(
                request.department_id
            ),
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{user_id}/status",
    response_model=UserResponse,
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def update_user_status(
    user_id: UUID,

    request: (
        UpdateUserStatusRequest
    ),

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],

) -> UserResponse:
    result = await dispatcher.send(
        UpdateUserStatusCommand(
            user_id=user_id,
            is_active=(
                request.is_active
            ),
        )
    )

    return _to_response(
        result
    )


@router.delete(
    "/{user_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def delete_user(
    user_id: UUID,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],

) -> None:
    """Hard-delete a user. Cascades through FK constraints
    (refresh_tokens, user_roles, chat_sessions)."""
    await dispatcher.send(
        DeleteUserCommand(
            user_id=user_id
        )
    )