from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReviewAnswerResponse(
    BaseModel
):
    feedback_id: UUID
    status: str
    review_result: str
    review_note: str | None

    reviewed_by_user_id: UUID
    reviewed_at: datetime