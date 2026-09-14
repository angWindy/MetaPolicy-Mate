from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AskQuestionCommand:
    user_id: UUID

    message: str

    session_id: UUID | None = None


@dataclass(frozen=True)
class AskQuestionResult:
    session_id: UUID

    turn_id: UUID

    answer: str

    citations: list[dict]

    warnings: list[str]

    confidence: str