from datetime import date

from pydantic import (
    BaseModel,
    Field,
)


class CreateDocumentSectionVersionRequest(
    BaseModel
):
    content: str = Field(
        min_length=1,
    )

    effective_from: date

    effective_to: date | None = None

    is_current: bool = False