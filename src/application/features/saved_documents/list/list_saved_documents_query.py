from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ListSavedDocumentsQuery:
    user_id: UUID
    page: int
    page_size: int
