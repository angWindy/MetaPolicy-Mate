from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)

from src.application.features.rbac.get_permissions.get_permissions_query import (
    GetPermissionsQuery,
)
from src.application.features.rbac.get_role_permissions.get_role_permissions_query import (
    GetRolePermissionsQuery,
)
from src.application.features.rbac.get_user_permissions.get_user_permissions_query import (
    GetUserPermissionsQuery,
)
from src.application.features.rbac.get_user_roles.get_user_roles_query import (
    GetUserRolesQuery,
)
from src.application.features.rbac.update_role_permissions.update_role_permissions_command import (
    UpdateRolePermissionsCommand,
)
from src.application.features.rbac.update_user_roles.update_user_roles_command import (
    UpdateUserRolesCommand,
)

from src.presentation.api.contracts.rbac.permission_response import (
    PermissionResponse,
)
from src.presentation.api.contracts.rbac.update_role_permissions_request import (
    UpdateRolePermissionsRequest,
)
from src.presentation.api.contracts.rbac.update_user_roles_request import (
    UpdateUserRolesRequest,
)
from src.presentation.api.contracts.roles.role_response import (
    RoleResponse,
)

from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)


router = APIRouter()


def _permission_response(
    item,
) -> PermissionResponse:
    return PermissionResponse(
        id=item.id,
        code=item.code,
        name=item.name,
        module=item.module,
        description=item.description,
    )


def _role_response(
    item,
) -> RoleResponse:
    return RoleResponse(
        id=item.id,
        code=item.code,
        name=item.name,
        description=item.description,
        is_system=item.is_system,
        created_at=item.created_at,
    )


@router.get(
    "/permissions",
    response_model=list[
        PermissionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def get_permissions(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    module: Annotated[
        str | None,
        Query(
            max_length=100
        ),
    ] = None,
) -> list[
    PermissionResponse
]:
    result = await dispatcher.send(
        GetPermissionsQuery(
            module=module
        )
    )

    return [
        _permission_response(item)
        for item in result
    ]


@router.get(
    "/roles/{role_id}/permissions",
    response_model=list[
        PermissionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def get_role_permissions(
    role_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[
    PermissionResponse
]:
    result = await dispatcher.send(
        GetRolePermissionsQuery(
            role_id=role_id
        )
    )

    return [
        _permission_response(item)
        for item in result
    ]


@router.put(
    "/roles/{role_id}/permissions",
    response_model=list[
        PermissionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def update_role_permissions(
    role_id: UUID,
    request: (
        UpdateRolePermissionsRequest
    ),
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> list[
    PermissionResponse
]:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Authentication required."
            ),
        )

    result = await dispatcher.send(
        UpdateRolePermissionsCommand(
            actor_user_id=(
                current_user.user_id
            ),
            role_id=role_id,
            permission_ids=(
                request.permission_ids
            ),
        )
    )

    return [
        _permission_response(item)
        for item in result
    ]


@router.get(
    "/users/{user_id}/roles",
    response_model=list[
        RoleResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def get_user_roles(
    user_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[
    RoleResponse
]:
    result = await dispatcher.send(
        GetUserRolesQuery(
            user_id=user_id
        )
    )

    return [
        _role_response(item)
        for item in result
    ]


@router.put(
    "/users/{user_id}/roles",
    response_model=list[
        RoleResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def update_user_roles(
    user_id: UUID,
    request: UpdateUserRolesRequest,
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> list[
    RoleResponse
]:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Authentication required."
            ),
        )

    result = await dispatcher.send(
        UpdateUserRolesCommand(
            actor_user_id=(
                current_user.user_id
            ),
            user_id=user_id,
            role_ids=(
                request.role_ids
            ),
        )
    )

    return [
        _role_response(item)
        for item in result
    ]


@router.get(
    "/users/{user_id}/permissions",
    response_model=list[
        PermissionResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "rbac.manage"
            )
        )
    ],
)
async def get_user_permissions(
    user_id: UUID,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[
    PermissionResponse
]:
    result = await dispatcher.send(
        GetUserPermissionsQuery(
            user_id=user_id
        )
    )

    return [
        _permission_response(item)
        for item in result
    ]