from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from src.application.common.interfaces.current_user import (
    CurrentUser,
)
from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.hybrid_retrieval.search.hybrid_search_query import (
    HybridSearchQuery,
)
from src.domain.repositories.department_repository import (
    DepartmentRepository,
)
from src.domain.repositories.role_repository import (
    RoleRepository,
)
from src.domain.repositories.user_repository import (
    UserRepository,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.contracts.retrieval.hybrid_search_request import (
    HybridSearchRequest,
)
from src.presentation.api.contracts.retrieval.hybrid_search_response import (
    HybridSearchItemResponse,
    HybridSearchResponse,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)
from src.presentation.api.dependencies.chat_rate_limit import (
    rate_limit_by_user,
)

router = APIRouter()


@router.post(
    "/search",
    response_model=(
        HybridSearchResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            rate_limit_by_user(
                bucket="search",
                max_requests=60,
                window_seconds=60,
            )
        ),
    ],
)
async def hybrid_search(
    request: HybridSearchRequest,

    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],

    scope: Annotated[
        ServiceContainer,
        Depends(get_request_scope),
    ],

    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> HybridSearchResponse:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Authentication required.",
        )

    user_repository = (
        scope.get_required(
            UserRepository
        )
    )

    user = await (
        user_repository.get_by_id(
            current_user.user_id
        )
    )

    if user is None:
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="User not found.",
        )

    department_code = ""

    if (
        user.department_id
        is not None
    ):
        department_repository = (
            scope.get_required(
                DepartmentRepository
            )
        )

        department = await (
            department_repository
            .get_by_id(
                user.department_id
            )
        )

        if department is not None:
            department_code = (
                department.code
            )

    role_repository = (
        scope.get_required(
            RoleRepository
        )
    )

    user_roles = await (
        role_repository.get_by_user_id(
            current_user.user_id
        )
    )

    roles = {
        role.code.strip().lower()
        for role in user_roles
        if role.code.strip()
    }

    if not roles:
        roles = {"staff"}

    result = await dispatcher.send(
        HybridSearchQuery(
            query=request.query,
            user_id=current_user.user_id,

            department_id=user.department_id,

            department=department_code,
            roles=roles,
            as_of_date=request.as_of_date,
        )
    )

    return HybridSearchResponse(
        query=result.query,
        has_evidence=(
            result.has_evidence
        ),
        items=[
            HybridSearchItemResponse(
                chunk_id=(
                    item.chunk_id
                ),
                text=item.text,
                score=item.score,
                source=item.source,
                metadata=item.metadata,
            )
            for item in result.items
        ],
    )