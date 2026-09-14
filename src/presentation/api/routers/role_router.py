from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    status,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.roles.create.create_role_command import (
    CreateRoleCommand,
)
from src.application.features.roles.delete.delete_role_command import (
    DeleteRoleCommand,
)
from src.application.features.roles.get_detail.get_role_query import (
    GetRoleQuery,
)
from src.application.features.roles.get_list.get_roles_query import (
    GetRolesQuery,
)
from src.application.features.roles.update.update_role_command import (
    UpdateRoleCommand,
)

from src.presentation.api.contracts.roles.create_role_request import (
    CreateRoleRequest,
)
from src.presentation.api.contracts.roles.role_response import (
    RoleResponse,
)
from src.presentation.api.contracts.roles.update_role_request import (
    UpdateRoleRequest,
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
) -> RoleResponse:
    return RoleResponse(
        id=item.id,
        code=item.code,
        name=item.name,

        description=(
            item.description
        ),

        is_system=(
            item.is_system
        ),

        created_at=(
            item.created_at
        ),
    )


@router.get(
    "",
    response_model=list[
        RoleResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "role.manage"
            )
        )
    ],
)
async def get_roles(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> list[RoleResponse]:
    result = await dispatcher.send(
        GetRolesQuery()
    )

    return [
        _to_response(item)
        for item in result
    ]


@router.get(
    "/{role_id}",
    response_model=RoleResponse,
    dependencies=[
        Depends(
            require_permission(
                "role.manage"
            )
        )
    ],
)
async def get_role(
    role_id: UUID,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> RoleResponse:
    result = await dispatcher.send(
        GetRoleQuery(
            role_id=role_id
        )
    )

    return _to_response(
        result
    )


@router.post(
    "",
    response_model=RoleResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
    dependencies=[
        Depends(
            require_permission(
                "role.manage"
            )
        )
    ],
)
async def create_role(
    request: CreateRoleRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> RoleResponse:
    result = await dispatcher.send(
        CreateRoleCommand(
            code=request.code,
            name=request.name,

            description=(
                request.description
            ),
        )
    )

    return _to_response(
        result
    )


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
    dependencies=[
        Depends(
            require_permission(
                "role.manage"
            )
        )
    ],
)
async def update_role(
    role_id: UUID,

    request: UpdateRoleRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> RoleResponse:
    result = await dispatcher.send(
        UpdateRoleCommand(
            role_id=role_id,

            name=request.name,

            description=(
                request.description
            ),
        )
    )

    return _to_response(
        result
    )


@router.delete(
    "/{role_id}",
    status_code=(
        status.HTTP_204_NO_CONTENT
    ),
    dependencies=[
        Depends(
            require_permission(
                "role.manage"
            )
        )
    ],
)
async def delete_role(
    role_id: UUID,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> None:
    """Hard-delete a custom (non-system) role. System roles are protected
    and must be unassigned from users first."""
    await dispatcher.send(
        DeleteRoleCommand(
            role_id=role_id
        )
    )