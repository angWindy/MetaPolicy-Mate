from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ChatSessionResponse(BaseModel):
    """Lightweight session info for listing."""

    session_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    turn_count: int = 0


class ChatTurnResponse(BaseModel):
    """Single turn within a session."""

    turn_id: UUID
    question: str
    answer: str
    citations: list[dict]
    created_at: datetime


class ChatSessionWithTurnsResponse(BaseModel):
    """Full session with all turns for loading a session."""

    session_id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime
    turns: list[ChatTurnResponse]
