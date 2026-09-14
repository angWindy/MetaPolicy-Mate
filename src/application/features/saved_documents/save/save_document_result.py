from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SaveDocumentResult:
    id: UUID
    user_id: UUID
    document_id: UUID
    created_at: datetime
