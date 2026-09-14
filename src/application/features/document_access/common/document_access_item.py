from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)


@dataclass(frozen=True)
class DocumentAccessItem:
    document_id: UUID

    access_scope: DocumentAccessScope

    department_ids: list[UUID]

    department_codes: list[str]