from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReviewAnswerCommand:
    feedback_id: UUID
    reviewer_user_id: UUID

    review_result: str
    review_note: str | None