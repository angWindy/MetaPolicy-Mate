from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from src.application.common.pipeline.interfaces.request_dispatcher import (
    RequestDispatcher,
)
from src.application.features.system_evaluation.get_flagged.get_flagged_answers_query import (
    GetFlaggedAnswersQuery,
)
from src.application.features.system_evaluation.get_summary.get_system_evaluation_summary_query import (
    GetSystemEvaluationSummaryQuery,
)
from src.application.features.system_evaluation.review_answer.review_answer_command import (
    ReviewAnswerCommand,
)
from src.presentation.api.contracts.system_evaluation.flagged_answer_response import (
    FlaggedAnswerListResponse,
    FlaggedAnswerResponse,
)
from src.presentation.api.contracts.system_evaluation.review_answer_request import (
    ReviewAnswerRequest,
)
from src.presentation.api.contracts.system_evaluation.review_answer_response import (
    ReviewAnswerResponse,
)
from src.presentation.api.contracts.system_evaluation.system_evaluation_summary_response import (
    SystemEvaluationSummaryResponse,
)
from src.presentation.api.dependencies.authorization import (
    require_permission,
)
from src.presentation.api.dependencies.authentication import (
    get_current_user,
)
from src.presentation.api.dependencies.request_dispatcher import (
    get_request_dispatcher,
    get_request_dispatcher_with_context,
)
from src.presentation.api.dependencies.document_access import (
    get_current_department_id,
    require_feedback_document_access,
)

router = APIRouter()


@router.get(
    "/summary",
    response_model=(
        SystemEvaluationSummaryResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.audit.read"
            )
        )
    ],
)
async def get_summary(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
) -> SystemEvaluationSummaryResponse:
    result = await dispatcher.send(
        GetSystemEvaluationSummaryQuery()
    )

    return (
        SystemEvaluationSummaryResponse(
            total_answers=(
                result.total_answers
            ),
            total_feedback=(
                result.total_feedback
            ),
            flagged_answers=(
                result.flagged_answers
            ),
            reviewed_answers=(
                result.reviewed_answers
            ),
            correct_answers=(
                result.correct_answers
            ),
            incorrect_answers=(
                result.incorrect_answers
            ),
            partially_correct_answers=(
                result
                .partially_correct_answers
            ),
            feedback_rate=(
                result.feedback_rate
            ),
            confirmed_error_rate=(
                result
                .confirmed_error_rate
            ),
        )
    )


@router.get(
    "/flagged-answers",
    response_model=(
        FlaggedAnswerListResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.audit.read"
            )
        )
    ],
)
async def get_flagged_answers(
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher
        ),
    ],
    department_id: Annotated[
        UUID | None,
        Depends(
            get_current_department_id
        ),
    ],
    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=100,
        ),
    ] = 20,
) -> FlaggedAnswerListResponse:
    result = await dispatcher.send(
        GetFlaggedAnswersQuery(
            page=page,
            page_size=page_size,
            department_id=department_id,
        )
    )

    return FlaggedAnswerListResponse(
        items=[
            FlaggedAnswerResponse(
                feedback_id=(
                    item.feedback_id
                ),
                turn_id=item.turn_id,
                session_id=(
                    item.session_id
                ),
                question=item.question,
                answer=item.answer,
                citations=item.citations,
                feedback_type=(
                    item.feedback_type
                ),
                comment=item.comment,
                status=item.status,
                reported_by_user_id=(
                    item
                    .reported_by_user_id
                ),
                created_at=(
                    item.created_at
                ),
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.put(
    "/feedback/{feedback_id}/review",
    response_model=(
        ReviewAnswerResponse
    ),
    dependencies=[
        Depends(
            require_permission(
                "document.audit.read"
            )
        ),
        Depends(
            require_feedback_document_access
        ),
    ],
)
async def review_answer(
    feedback_id: UUID,
    request: ReviewAnswerRequest,
    dispatcher: Annotated[
        RequestDispatcher,
        Depends(
            get_request_dispatcher_with_context
        ),
    ],
    current_user=Depends(
        get_current_user
    ),
) -> ReviewAnswerResponse:
    result = await dispatcher.send(
        ReviewAnswerCommand(
            feedback_id=feedback_id,
            reviewer_user_id=(
                current_user.user_id
            ),
            review_result=(
                request.review_result
            ),
            review_note=(
                request.review_note
            ),
        )
    )

    return ReviewAnswerResponse(
        feedback_id=(
            result.feedback_id
        ),
        status=result.status,
        review_result=(
            result.review_result
        ),
        review_note=(
            result.review_note
        ),
        reviewed_by_user_id=(
            result.reviewed_by_user_id
        ),
        reviewed_at=(
            result.reviewed_at
        ),
    )