from typing import Optional

from pydantic import BaseModel, Field


class ReviewDocumentRequest(BaseModel):
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Ghi chú xem xét (tùy chọn)",
    )
