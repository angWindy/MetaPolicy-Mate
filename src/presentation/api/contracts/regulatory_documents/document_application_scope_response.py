from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.enums.document_reference_nature import (
    DocumentReferenceNature,
)


class DocumentApplicationScopeResponse(
    BaseModel
):
    id: UUID

    source_document_id: UUID
    source_version_id: UUID

    related_document_id: UUID

    scope_type: ApplicationScopeType
    scope_detail: str | None

    reference_nature: (
        DocumentReferenceNature
    )

    created_by: UUID | None
    created_at: datetime