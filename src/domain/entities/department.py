from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Department:
    id: UUID

    code: str
    name: str

    is_active: bool = True

    created_at: datetime | None = None
    updated_at: datetime | None = None