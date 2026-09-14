from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


@dataclass
class DocumentEffectivenessAlert:
    id: UUID

    new_document_number: str
    new_document_title: str

    announced_date: date | None
    effective_date: date | None

    affected_document_id: UUID

    status: (
        DocumentEffectivenessAlertStatus
    )

    note: str | None

    created_by: UUID | None

    created_at: datetime
    updated_at: datetime | None