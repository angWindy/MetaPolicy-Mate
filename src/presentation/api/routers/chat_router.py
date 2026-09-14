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
from src.application.features.chat.ask.ask_question_command import (
    AskQuestionCommand,
)

from src.presentation.api.contracts.chat.chat_request import (
    ChatRequest,
)
from src.presentation.api.contracts.chat.chat_response import (
    ChatResponse,
)
from src.presentation.api.contracts.chat.chat_session_response import (
    ChatSessionResponse,
    ChatSessionWithTurnsResponse,
    ChatTurnResponse,
)

from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher_with_context,
)
from src.presentation.api.dependencies.chat_repository import (
    get_chat_repository,
)
from uuid import UUID

from src.application.features.answer_feedback.report.report_answer_command import (
    ReportAnswerCommand,
)
from src.presentation.api.contracts.answer_feedback.report_answer_request import (
    ReportAnswerRequest,
)
from src.presentation.api.contracts.answer_feedback.report_answer_response import (
    ReportAnswerResponse,
)
from collections.abc import (
    AsyncIterator,
)

from src.application.common.interfaces.chat_rate_limiter import (
    ChatRateLimiter,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.infrastructure.dependency_injection.service_container import (
    ServiceContainer,
)
from src.presentation.api.dependencies.request_scope import (
    get_request_scope,
)

router = APIRouter()

async def enforce_chat_guard(
    current_user: Annotated[
        CurrentUser,
        Depends(
            get_current_user
        ),
    ],
    scope: Annotated[
        ServiceContainer,
        Depends(
            get_request_scope
        ),
    ],
) -> AsyncIterator[None]:
    user_id = (
        current_user.user_id
    )

    if user_id is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Authentication required."
            ),
        )

    limiter = scope.get_required(
        ChatRateLimiter
    )

    allowed, retry_after = await (
        limiter.check(
            user_id
        )
    )

    if not allowed:
        raise HTTPException(
            status_code=(
                status
                .HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many chat requests. "
                "Please try again later."
            ),
            headers={
                "Retry-After": str(
                    retry_after
                )
            },
        )

    lock_token = await (
        limiter.acquire_lock(
            user_id
        )
    )

    if lock_token is None:
        raise HTTPException(
            status_code=(
                status
                .HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Another chat request "
                "is already being processed."
            ),
            headers={
                "Retry-After": "2"
            },
        )

    try:
        yield

    finally:
        await limiter.release_lock(
            user_id,
            lock_token,
        )


@router.post(
    "",
    response_model=ChatResponse,
    dependencies=[
        Depends(
            require_permission(
                "document.read"
            )
        ),
        Depends(
            enforce_chat_guard
        ),
    ],
)
async def ask_question(
    request: ChatRequest,

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
) -> ChatResponse:
    if (
        current_user.user_id
        is None
    ):
        raise HTTPException(
            status_code=(
                status
                .HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Authentication required."
            ),
        )

    result = await (
        dispatcher.send(
            AskQuestionCommand(
                user_id=(
                    current_user
                    .user_id
                ),
                message=(
                    request.message
                ),
                session_id=(
                    request
                    .session_id
                ),
            )
        )
    )

    return ChatResponse(
        session_id=(
            result.session_id
        ),
        turn_id=result.turn_id,
        answer=result.answer,
        citations=(
            result.citations
        ),
        warnings=(
            result.warnings
        ),
        confidence=(
            result.confidence
        ),
    )

@router.post(
    "/turns/{turn_id}/report",
    response_model=ReportAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_answer(
    turn_id: UUID,
    request: ReportAnswerRequest,

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
) -> ReportAnswerResponse:
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
        ReportAnswerCommand(
            turn_id=turn_id,
            reported_by_user_id=(
                current_user.user_id
            ),
            comment=request.comment,
        )
    )

    return ReportAnswerResponse(
        feedback_id=(
            result.feedback_id
        ),
        turn_id=(
            result.turn_id
        ),
        feedback_type=(
            result.feedback_type
        ),
        comment=(
            result.comment
        ),
        status=(
            result.status
        ),
        created_at=(
            result.created_at
        ),
    )


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
)
async def list_chat_sessions(
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    chat_repo: Annotated[
        ChatRepository,
        Depends(get_chat_repository),
    ],
) -> list[ChatSessionResponse]:
    """List all chat sessions for the current user."""
    if current_user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    sessions = await chat_repo.list_sessions(current_user.user_id)
    result: list[ChatSessionResponse] = []
    for session in sessions:
        turn_count = await chat_repo.count_turns_in_session(session.id)
        result.append(
            ChatSessionResponse(
                session_id=session.id,
                user_id=session.user_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                turn_count=turn_count,
            )
        )
    return result


@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionWithTurnsResponse,
)
async def get_chat_session(
    session_id: UUID,
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    chat_repo: Annotated[
        ChatRepository,
        Depends(get_chat_repository),
    ],
) -> ChatSessionWithTurnsResponse:
    """Get a specific chat session with all its turns."""
    if current_user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    session = await chat_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    # Authorization: user must own this session
    if session.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this session.",
        )

    turns = await chat_repo.list_turns(session_id)
    return ChatSessionWithTurnsResponse(
        session_id=session.id,
        user_id=session.user_id,
        created_at=session.created_at,
        updated_at=session.updated_at,
        turns=[
            ChatTurnResponse(
                turn_id=t.id,
                question=t.question,
                answer=t.answer,
                citations=t.citations,
                created_at=t.created_at,
            )
            for t in turns
        ],
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_chat_session(
    session_id: UUID,
    current_user: Annotated[
        CurrentUser,
        Depends(get_current_user),
    ],
    chat_repo: Annotated[
        ChatRepository,
        Depends(get_chat_repository),
    ],
) -> None:
    """Delete a chat session and all its turns."""
    if current_user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    session = await chat_repo.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    # Authorization: user must own this session
    if session.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this session.",
        )

    await chat_repo.delete_session(session_id)