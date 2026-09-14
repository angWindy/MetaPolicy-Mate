from uuid import UUID

from pydantic import (
    BaseModel,
)


class ChatResponse(
    BaseModel
):
    session_id: UUID

    turn_id: UUID

    answer: str

    citations: list[dict]

    warnings: list[str]

    confidence: str