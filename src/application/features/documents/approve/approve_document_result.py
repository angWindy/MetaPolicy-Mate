from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.schemas import ProcessingStatus


@dataclass(frozen=True)
class ApproveDocumentResult:
    version_id: UUID
    status: ProcessingStatus
    approved_at: datetime
