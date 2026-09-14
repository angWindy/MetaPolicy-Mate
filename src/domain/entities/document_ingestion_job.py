from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class DocumentIngestionJob:
    id: UUID

    version_id: UUID

    status: str

    warnings: list[str]

    error_message: str | None

    section_count: int
    chunk_count: int

    started_at: datetime
    completed_at: datetime | None