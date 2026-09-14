from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SavedDocumentItem:
    id: UUID
    document_id: UUID
    created_at: datetime


@dataclass(frozen=True)
class ListSavedDocumentsResult:
    items: list[SavedDocumentItem]
    total: int
    page: int
    page_size: int
