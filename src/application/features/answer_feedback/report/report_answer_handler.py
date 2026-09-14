from datetime import datetime, timezone
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.forbidden_exception import (
    ForbiddenException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.answer_feedback.report.report_answer_command import (
    ReportAnswerCommand,
)
from src.application.features.answer_feedback.report.report_answer_result import (
    ReportAnswerResult,
)
from src.domain.entities.answer_feedback import (
    AnswerFeedback,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)


class ReportAnswerHandler(
    RequestHandler[
        ReportAnswerCommand,
        ReportAnswerResult,
    ]
):
    def __init__(
        self,
        chat_repository: ChatRepository,
        feedback_repository: AnswerFeedbackRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._chat_repository = chat_repository
        self._feedback_repository = feedback_repository
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: ReportAnswerCommand,
    ) -> ReportAnswerResult:
        turn = await self._chat_repository.get_turn(
            request.turn_id
        )

        if turn is None:
            raise NotFoundException(
                "Chat turn not found."
            )

        session = await self._chat_repository.get_session(
            turn.session_id
        )

        if session is None:
            raise NotFoundException(
                "Chat session not found."
            )

        if (
            session.user_id
            != request.reported_by_user_id
        ):
            raise ForbiddenException(
                "You cannot report an answer "
                "from another user's session."
            )

        existing = await (
            self._feedback_repository
            .get_by_turn_and_reporter(
                turn_id=request.turn_id,
                reported_by_user_id=(
                    request.reported_by_user_id
                ),
            )
        )

        if existing is not None:
            raise ConflictException(
                "This answer has already been reported."
            )

        now = datetime.now(
            timezone.utc
        )

        feedback = AnswerFeedback(
            id=uuid4(),
            turn_id=request.turn_id,
            reported_by_user_id=(
                request.reported_by_user_id
            ),
            feedback_type="INCORRECT",
            comment=(
                request.comment.strip()
                if request.comment
                else None
            ),
            status="FLAGGED",
            review_result=None,
            review_note=None,
            created_at=now,
            reviewed_at=None,
            reviewed_by_user_id=None,
        )

        await self._feedback_repository.add(
            feedback
        )

        await self._unit_of_work.save_changes()

        return ReportAnswerResult(
            feedback_id=feedback.id,
            turn_id=feedback.turn_id,
            feedback_type=(
                feedback.feedback_type
            ),
            comment=feedback.comment,
            status=feedback.status,
            created_at=feedback.created_at,
        )