from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReportAnswerCommand:
    turn_id: UUID
    reported_by_user_id: UUID
    comment: str | None