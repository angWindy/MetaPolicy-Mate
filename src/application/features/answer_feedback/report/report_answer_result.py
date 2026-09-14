from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class ReportAnswerResult:
    feedback_id: UUID
    turn_id: UUID
    feedback_type: str
    comment: str | None
    status: str
    created_at: datetime