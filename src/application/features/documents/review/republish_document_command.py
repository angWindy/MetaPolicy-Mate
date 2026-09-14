from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RepublishDocumentCommand:
    version_id: UUID
    admin_id: UUID
    notes: str | None
