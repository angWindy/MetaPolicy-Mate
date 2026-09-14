from datetime import (
    date,
    datetime,
)
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


class RegulatoryDocumentResponse(
    BaseModel
):
    id: UUID

    document_number: str
    title: str
    issued_by: str

    issued_date: date
    effective_date: date

    legal_status: DocumentLegalStatus

    access_scope: DocumentAccessScope

    created_at: datetime | None
    updated_at: datetime | None

    # Computed display status for the admin/operator UI.
    # Maps canonical LegalStatus values to UI status labels.
    # FE reads this directly instead of inferring from legal_status.
    status: str
    updated_by: str | None = "—"

    class Config:
        # Allow extra fields from the router's _to_response() so we can
        # include computed fields that aren't in the DB entity.
        extra = "allow"