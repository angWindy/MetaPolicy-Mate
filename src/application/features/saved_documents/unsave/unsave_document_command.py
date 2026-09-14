from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class UnsaveDocumentCommand:
    user_id: UUID
    document_id: UUID
