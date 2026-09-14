from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class AnswerFeedback:
    id: UUID
    turn_id: UUID
    reported_by_user_id: UUID

    feedback_type: str
    comment: str | None

    status: str

    review_result: str | None
    review_note: str | None

    created_at: datetime

    reviewed_at: datetime | None
    reviewed_by_user_id: UUID | None