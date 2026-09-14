from src.application.common.document_access_policy import (
    citations_are_accessible,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.system_evaluation.get_flagged.flagged_answer_item import (
    FlaggedAnswerItem,
)
from src.application.features.system_evaluation.get_flagged.get_flagged_answers_query import (
    GetFlaggedAnswersQuery,
)
from src.application.features.system_evaluation.get_flagged.get_flagged_answers_result import (
    GetFlaggedAnswersResult,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.domain.repositories.chat_repository import (
    ChatRepository,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetFlaggedAnswersHandler(
    RequestHandler[
        GetFlaggedAnswersQuery,
        GetFlaggedAnswersResult,
    ]
):
    def __init__(
        self,
        feedback_repository: (
            AnswerFeedbackRepository
        ),
        chat_repository: (
            ChatRepository
        ),
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
    ) -> None:
        self._feedback_repository = (
            feedback_repository
        )

        self._chat_repository = (
            chat_repository
        )

        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

    async def handle(
        self,
        request: GetFlaggedAnswersQuery,
    ) -> GetFlaggedAnswersResult:
        items: list[
            FlaggedAnswerItem
        ] = []

        total = 0

        scan_page = 1

        batch_size = max(
            100,
            request.page_size,
        )

        page_start = (
            request.page - 1
        ) * request.page_size

        page_end = (
            page_start
            + request.page_size
        )

        while True:
            (
                feedbacks,
                raw_total,
            ) = await (
                self._feedback_repository
                .get_flagged(
                    page=scan_page,
                    page_size=batch_size,
                )
            )

            if not feedbacks:
                break

            for feedback in feedbacks:
                turn = await (
                    self._chat_repository
                    .get_turn(
                        feedback.turn_id
                    )
                )

                if turn is None:
                    continue

                allowed = await (
                    citations_are_accessible(
                        citations=list(
                            turn.citations
                        ),
                        department_id=(
                            request.department_id
                        ),
                        document_repository=(
                            self
                            ._document_repository
                        ),
                        document_department_repository=(
                            self
                            ._document_department_repository
                        ),
                    )
                )

                if not allowed:
                    # Fail closed:
                    # không được đưa question/answer
                    # của document không còn quyền
                    # truy cập vào kết quả review.
                    continue

                if (
                    page_start
                    <= total
                    < page_end
                ):
                    items.append(
                        FlaggedAnswerItem(
                            feedback_id=(
                                feedback.id
                            ),
                            turn_id=turn.id,
                            session_id=(
                                turn.session_id
                            ),
                            question=(
                                turn.question
                            ),
                            answer=turn.answer,
                            citations=list(
                                turn.citations
                            ),
                            feedback_type=(
                                feedback
                                .feedback_type
                            ),
                            comment=(
                                feedback.comment
                            ),
                            status=(
                                feedback.status
                            ),
                            reported_by_user_id=(
                                feedback
                                .reported_by_user_id
                            ),
                            created_at=(
                                feedback.created_at
                            ),
                        )
                    )

                total += 1

            if (
                scan_page
                * batch_size
                >= raw_total
            ):
                break

            scan_page += 1

        return GetFlaggedAnswersResult(
            items=items,
            total=total,
            page=request.page,
            page_size=request.page_size,
        )