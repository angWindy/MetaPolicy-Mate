from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.answer_feedback import (
    AnswerFeedback,
)
from src.domain.repositories.answer_feedback_repository import (
    AnswerFeedbackRepository,
)
from src.persistence.tenant.models.answer_feedback import (
    AnswerFeedbackModel,
)


class SqlAlchemyAnswerFeedbackRepository(
    AnswerFeedbackRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        feedback: AnswerFeedback,
    ) -> None:
        self._session.add(
            AnswerFeedbackModel(
                id=feedback.id,
                turn_id=feedback.turn_id,
                reported_by_user_id=(
                    feedback.reported_by_user_id
                ),
                feedback_type=(
                    feedback.feedback_type
                ),
                comment=feedback.comment,
                status=feedback.status,
                review_result=(
                    feedback.review_result
                ),
                review_note=(
                    feedback.review_note
                ),
                created_at=(
                    feedback.created_at
                ),
                reviewed_at=(
                    feedback.reviewed_at
                ),
                reviewed_by_user_id=(
                    feedback.reviewed_by_user_id
                ),
            )
        )

    async def get_by_id(
        self,
        feedback_id: UUID,
    ) -> AnswerFeedback | None:
        model = await self._session.get(
            AnswerFeedbackModel,
            feedback_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def update(
        self,
        feedback: AnswerFeedback,
    ) -> None:
        model = await self._session.get(
            AnswerFeedbackModel,
            feedback.id,
        )

        if model is None:
            return

        model.status = feedback.status

        model.review_result = (
            feedback.review_result
        )

        model.review_note = (
            feedback.review_note
        )

        model.reviewed_at = (
            feedback.reviewed_at
        )

        model.reviewed_by_user_id = (
            feedback.reviewed_by_user_id
        )

    async def get_flagged(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[
        list[AnswerFeedback],
        int,
    ]:
        where_clause = (
            AnswerFeedbackModel.status
            == "FLAGGED"
        )

        total_result = await (
            self._session.execute(
                select(
                    func.count(
                        AnswerFeedbackModel.id
                    )
                ).where(
                    where_clause
                )
            )
        )

        result = await self._session.execute(
            select(
                AnswerFeedbackModel
            )
            .where(
                where_clause
            )
            .order_by(
                AnswerFeedbackModel
                .created_at
                .desc()
            )
            .offset(
                (page - 1)
                * page_size
            )
            .limit(page_size)
        )

        return (
            [
                self._to_domain(model)
                for model
                in result.scalars().all()
            ],
            int(
                total_result.scalar_one()
            ),
        )

    async def count_all(
        self,
    ) -> int:
        result = await self._session.execute(
            select(
                func.count(
                    AnswerFeedbackModel.id
                )
            )
        )

        return int(
            result.scalar_one()
        )

    async def count_by_status(
        self,
        status: str,
    ) -> int:
        result = await self._session.execute(
            select(
                func.count(
                    AnswerFeedbackModel.id
                )
            ).where(
                AnswerFeedbackModel.status
                == status
            )
        )

        return int(
            result.scalar_one()
        )

    async def count_by_review_result(
        self,
        review_result: str,
    ) -> int:
        result = await self._session.execute(
            select(
                func.count(
                    AnswerFeedbackModel.id
                )
            ).where(
                AnswerFeedbackModel.review_result
                == review_result
            )
        )

        return int(
            result.scalar_one()
        )

    @staticmethod
    def _to_domain(
        model: AnswerFeedbackModel,
    ) -> AnswerFeedback:
        return AnswerFeedback(
            id=model.id,
            turn_id=model.turn_id,
            reported_by_user_id=(
                model.reported_by_user_id
            ),
            feedback_type=(
                model.feedback_type
            ),
            comment=model.comment,
            status=model.status,
            review_result=(
                model.review_result
            ),
            review_note=(
                model.review_note
            ),
            created_at=model.created_at,
            reviewed_at=model.reviewed_at,
            reviewed_by_user_id=(
                model.reviewed_by_user_id
            ),
        )

    async def get_by_turn_and_reporter(
        self,
        turn_id: UUID,
        reported_by_user_id: UUID,
    ) -> AnswerFeedback | None:
        result = await self._session.execute(
            select(
                AnswerFeedbackModel
            ).where(
                AnswerFeedbackModel.turn_id
                == turn_id,
                AnswerFeedbackModel.reported_by_user_id
                == reported_by_user_id,
            )
        )

        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)