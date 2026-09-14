from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
)

from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.enums.document_reference_nature import (
    DocumentReferenceNature,
)


class CreateDocumentApplicationScopeRequest(
    BaseModel
):
    related_document_id: UUID

    scope_type: ApplicationScopeType

    scope_detail: str | None = (
        Field(
            default=None,
            max_length=4000,
        )
    )

    reference_nature: (
        DocumentReferenceNature
    )