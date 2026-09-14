from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Role:
    id: UUID
    code: str
    name: str

    description: str | None = None
    is_system: bool = False

    created_at: datetime | None = None