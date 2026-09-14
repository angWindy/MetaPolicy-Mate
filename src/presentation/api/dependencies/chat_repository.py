from typing import Annotated

from fastapi import Depends

from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)


async def get_chat_repository(
    scope: Annotated[
        ServiceContainer,
        Depends(get_request_scope),
    ],
) -> ChatRepository:
    """Resolve ChatRepository from the request scope."""
    return scope.get_required(ChatRepository)