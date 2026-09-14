from typing import Protocol
from uuid import UUID

from src.domain.entities.answer_feedback import (
    AnswerFeedback,
)


class AnswerFeedbackRepository(
    Protocol
):
    async def add(
        self,
        feedback: AnswerFeedback,
    ) -> None:
        ...

    async def get_by_id(
        self,
        feedback_id: UUID,
    ) -> AnswerFeedback | None:
        ...

    async def update(
        self,
        feedback: AnswerFeedback,
    ) -> None:
        ...

    async def get_flagged(
        self,
        *,
        page: int,
        page_size: int,
    ) -> tuple[
        list[AnswerFeedback],
        int,
    ]:
        ...

    async def count_all(
        self,
    ) -> int:
        ...

    async def count_by_status(
        self,
        status: str,
    ) -> int:
        ...

    async def count_by_review_result(
        self,
        review_result: str,
    ) -> int:
        ...

    async def get_by_turn_and_reporter(
        self,
        turn_id: UUID,
        reported_by_user_id: UUID,
    ) -> AnswerFeedback | None:
        ...