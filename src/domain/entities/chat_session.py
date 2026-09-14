from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class ChatSession:
    id: UUID

    user_id: UUID

    created_at: datetime

    updated_at: datetime