from pydantic import BaseModel, Field


class ReportAnswerRequest(BaseModel):
    comment: str | None = Field(
        default=None,
        max_length=2000,
    )