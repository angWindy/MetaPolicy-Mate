from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.schemas import ProcessingStatus


@dataclass(frozen=True)
class RepublishDocumentResult:
    version_id: UUID
    status: ProcessingStatus
    reviewed_at: datetime
