from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.system_evaluation.get_summary.get_system_evaluation_summary_query import (
    GetSystemEvaluationSummaryQuery,
)
from src.application.features.system_evaluation.get_summary.get_system_evaluation_summary_result import (
    GetSystemEvaluationSummaryResult,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)


class GetSystemEvaluationSummaryHandler(
    RequestHandler[
        GetSystemEvaluationSummaryQuery,
        GetSystemEvaluationSummaryResult,
    ]
):
    def __init__(
        self,
        chat_repository: ChatRepository,
        answer_feedback_repository: (
            AnswerFeedbackRepository
        ),
    ) -> None:
        self._chat_repository = (
            chat_repository
        )

        self._feedback_repository = (
            answer_feedback_repository
        )

    async def handle(
        self,
        request: (
            GetSystemEvaluationSummaryQuery
        ),
    ) -> GetSystemEvaluationSummaryResult:
        del request

        total_answers = await (
            self._chat_repository
            .count_turns()
        )

        total_feedback = await (
            self._feedback_repository
            .count_all()
        )

        flagged_answers = await (
            self._feedback_repository
            .count_by_status(
                "FLAGGED"
            )
        )

        reviewed_answers = await (
            self._feedback_repository
            .count_by_status(
                "REVIEWED"
            )
        )

        correct_answers = await (
            self._feedback_repository
            .count_by_review_result(
                "CORRECT"
            )
        )

        incorrect_answers = await (
            self._feedback_repository
            .count_by_review_result(
                "INCORRECT"
            )
        )

        partially_correct_answers = await (
            self._feedback_repository
            .count_by_review_result(
                "PARTIALLY_CORRECT"
            )
        )

        feedback_rate = (
            total_feedback / total_answers
            if total_answers > 0
            else 0.0
        )

        confirmed_error_rate = (
            incorrect_answers
            / reviewed_answers
            if reviewed_answers > 0
            else 0.0
        )

        return (
            GetSystemEvaluationSummaryResult(
                total_answers=total_answers,
                total_feedback=(
                    total_feedback
                ),
                flagged_answers=(
                    flagged_answers
                ),
                reviewed_answers=(
                    reviewed_answers
                ),
                correct_answers=(
                    correct_answers
                ),
                incorrect_answers=(
                    incorrect_answers
                ),
                partially_correct_answers=(
                    partially_correct_answers
                ),
                feedback_rate=(
                    round(
                        feedback_rate,
                        4,
                    )
                ),
                confirmed_error_rate=(
                    round(
                        confirmed_error_rate,
                        4,
                    )
                ),
            )
        )