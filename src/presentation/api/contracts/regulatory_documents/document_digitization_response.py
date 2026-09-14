from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DocumentDigitizationResponse(
    BaseModel
):
    version_id: UUID

    status: str

    section_count: int

    chunk_count: int

    warnings: list[str]

    error_message: str | None

    started_at: datetime

    completed_at: datetime | None