from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.domain.entities.document_effectiveness_alert import (
    DocumentEffectivenessAlert,
)
from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


@dataclass(frozen=True)
class DocumentEffectivenessAlertItem:
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

    effective_date_reached: bool

    @staticmethod
    def from_entity(
        entity: DocumentEffectivenessAlert,
    ) -> "DocumentEffectivenessAlertItem":
        effective_date_reached = (
            entity.effective_date is not None
            and entity.effective_date
            <= date.today()
        )

        return DocumentEffectivenessAlertItem(
            id=entity.id,
            new_document_number=(
                entity.new_document_number
            ),
            new_document_title=(
                entity.new_document_title
            ),
            announced_date=(
                entity.announced_date
            ),
            effective_date=(
                entity.effective_date
            ),
            affected_document_id=(
                entity.affected_document_id
            ),
            status=entity.status,
            note=entity.note,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            effective_date_reached=(
                effective_date_reached
            ),
        )