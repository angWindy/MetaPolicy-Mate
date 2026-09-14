from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class FlaggedAnswerItem:
    feedback_id: UUID

    turn_id: UUID
    session_id: UUID

    question: str
    answer: str
    citations: list[dict]

    feedback_type: str
    comment: str | None
    status: str

    reported_by_user_id: UUID

    created_at: datetime