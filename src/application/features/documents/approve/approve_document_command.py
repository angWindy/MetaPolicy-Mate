from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ApproveDocumentCommand:
    version_id: UUID
