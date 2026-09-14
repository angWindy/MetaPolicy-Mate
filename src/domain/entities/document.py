from dataclasses import dataclass
from datetime import (
    date,
    datetime,
)
from uuid import UUID

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


@dataclass
class Document:
    id: UUID

    document_number: str
    title: str
    issued_by: str

    issued_date: date
    effective_date: date

    legal_status: DocumentLegalStatus

    access_scope: DocumentAccessScope = (
        DocumentAccessScope.PUBLIC
    )

    created_at: datetime | None = None
    updated_at: datetime | None = None