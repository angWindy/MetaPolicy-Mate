from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReportAnswerResponse(BaseModel):
    feedback_id: UUID
    turn_id: UUID
    feedback_type: str
    comment: str | None
    status: str
    created_at: datetime