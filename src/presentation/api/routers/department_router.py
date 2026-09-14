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
from src.application.features.departments.create.create_department_command import (
    CreateDepartmentCommand,
)
from src.application.features.departments.update.update_department_command import (
    UpdateDepartmentCommand,
)
from src.application.features.departments.get_list.get_departments_query import (
    GetDepartmentsQuery,
)
from src.presentation.api.contracts.departments.create_department_request import (
    CreateDepartmentRequest,
)
from src.presentation.api.contracts.departments.update_department_request import (
    UpdateDepartmentRequest,
)
from src.presentation.api.contracts.departments.department_response import (
    DepartmentResponse,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher_with_context,
)


router = APIRouter()


@router.get(
    "",
    response_model=list[
        DepartmentResponse
    ],
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def get_departments(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> list[DepartmentResponse]:
    result = await dispatcher.send(
        GetDepartmentsQuery()
    )

    return [
        DepartmentResponse(
            id=item.id,
            code=item.code,
            name=item.name,
            is_active=item.is_active,
        )
        for item in result
    ]


@router.post(
    "",
    response_model=DepartmentResponse,
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
async def create_department(
    request: CreateDepartmentRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DepartmentResponse:
    result = await dispatcher.send(
        CreateDepartmentCommand(
            code=request.code,
            name=request.name,
        )
    )

    return DepartmentResponse(
        id=result.id,
        code=result.code,
        name=result.name,
        is_active=result.is_active,
    )


@router.put(
    "/{department_id}",
    response_model=DepartmentResponse,
    dependencies=[
        Depends(
            require_permission(
                "user.manage"
            )
        )
    ],
)
async def update_department(
    department_id: UUID,
    request: UpdateDepartmentRequest,

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
) -> DepartmentResponse:
    result = await dispatcher.send(
        UpdateDepartmentCommand(
            department_id=str(department_id),
            name=request.name,
            is_active=request.is_active,
        )
    )

    return DepartmentResponse(
        id=result.id,
        code=result.code,
        name=result.name,
        is_active=result.is_active,
    )