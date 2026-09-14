from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


@dataclass(frozen=True)
class GetRegulatoryDocumentsQuery:
    document_number: str | None = None

    legal_status: (
        DocumentLegalStatus | None
    ) = None

    issued_from: date | None = None
    issued_to: date | None = None

    department_id: UUID | None = None

    is_admin: bool = False

    page: int = 1
    page_size: int = 20