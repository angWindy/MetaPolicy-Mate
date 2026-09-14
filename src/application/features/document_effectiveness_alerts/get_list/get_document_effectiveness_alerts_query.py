from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


@dataclass(frozen=True)
class GetDocumentEffectivenessAlertsQuery:
    status: (
        DocumentEffectivenessAlertStatus
        | None
    ) = None

    page: int = 1
    page_size: int = 20

    department_id: UUID | None = None