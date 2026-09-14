from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ChatTurn:
    id: UUID

    session_id: UUID

    question: str

    answer: str

    citations: list[dict]

    created_at: datetime