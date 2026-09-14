from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from uuid import UUID


@dataclass(frozen=True)
class DocumentSectionVersionDto:
    id: UUID
    section_id: UUID

    version_number: int

    content: str

    effective_from: date
    effective_to: date | None

    is_current: bool

    created_at: datetime
    updated_at: datetime | None