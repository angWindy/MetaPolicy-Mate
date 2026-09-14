from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from uuid import UUID

from src.domain.entities.document import (
    Document,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


@dataclass(frozen=True)
class RegulatoryDocumentItem:
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

    @staticmethod
    def from_document(
        document: Document,
    ) -> "RegulatoryDocumentItem":
        return RegulatoryDocumentItem(
            id=document.id,
            document_number=(
                document.document_number
            ),
            title=document.title,
            issued_by=document.issued_by,
            issued_date=document.issued_date,
            effective_date=(
                document.effective_date
            ),
            legal_status=(
                document.legal_status
            ),
            access_scope=(
                document.access_scope
            ),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )