from datetime import (
    datetime,
    timezone,
)

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.exceptions.request_validation_exception import (
    RequestValidationException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.system_evaluation.review_answer.review_answer_command import (
    ReviewAnswerCommand,
)
from src.application.features.system_evaluation.review_answer.review_answer_result import (
    ReviewAnswerResult,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.shared.validation_error import (
    ValidationError,
)

class ReviewAnswerHandler(
    RequestHandler[
        ReviewAnswerCommand,
        ReviewAnswerResult,
    ]
):
    def __init__(
        self,
        feedback_repository: (
            AnswerFeedbackRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._feedback_repository = (
            feedback_repository
        )

        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: ReviewAnswerCommand,
    ) -> ReviewAnswerResult:
        feedback = await (
            self._feedback_repository
            .get_by_id(
                request.feedback_id
            )
        )

        if feedback is None:
            raise NotFoundException(
                "Answer feedback not found."
            )

        review_result = (
            request.review_result
            .strip()
            .upper()
        )

        allowed_results = {
            "CORRECT",
            "INCORRECT",
            "PARTIALLY_CORRECT",
        }

        if (
            review_result
            not in allowed_results
        ):
            raise RequestValidationException(
                [
                    ValidationError(
                        property_name=(
                            "review_result"
                        ),
                        error_message=(
                            "review_result must be "
                            "CORRECT, INCORRECT, or "
                            "PARTIALLY_CORRECT."
                        ),
                    )
                ]
            )

        now = datetime.now(
            timezone.utc
        )

        feedback.status = "REVIEWED"

        feedback.review_result = (
            review_result
        )

        feedback.review_note = (
            request.review_note.strip()
            if request.review_note
            else None
        )

        feedback.reviewed_at = now

        feedback.reviewed_by_user_id = (
            request.reviewer_user_id
        )

        await (
            self._feedback_repository
            .update(feedback)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return ReviewAnswerResult(
            feedback_id=feedback.id,
            status=feedback.status,
            review_result=review_result,
            review_note=(
                feedback.review_note
            ),
            reviewed_by_user_id=(
                request.reviewer_user_id
            ),
            reviewed_at=now,
        )