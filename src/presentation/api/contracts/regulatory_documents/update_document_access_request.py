from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
)

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)


class UpdateDocumentAccessRequest(
    BaseModel
):
    access_scope: (
        DocumentAccessScope
    )

    department_ids: list[
        UUID
    ] = Field(
        default_factory=list
    )