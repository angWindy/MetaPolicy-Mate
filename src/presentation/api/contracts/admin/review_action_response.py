from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.schemas import ProcessingStatus


class ReviewActionResponse(BaseModel):
    version_id: UUID
    status: ProcessingStatus
    reviewed_at: datetime
