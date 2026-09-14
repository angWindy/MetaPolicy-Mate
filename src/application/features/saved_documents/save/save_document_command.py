from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class SaveDocumentCommand:
    user_id: UUID
    document_id: UUID
