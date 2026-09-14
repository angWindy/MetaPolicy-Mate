from datetime import date
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
)


class CreateDocumentEffectivenessAlertRequest(
    BaseModel
):
    new_document_number: str = (
        Field(
            min_length=1,
            max_length=100,
        )
    )

    new_document_title: str = (
        Field(
            min_length=1,
            max_length=500,
        )
    )

    announced_date: date | None = None
    effective_date: date | None = None

    affected_document_id: UUID

    note: str | None = Field(
        default=None,
        max_length=2000,
    )