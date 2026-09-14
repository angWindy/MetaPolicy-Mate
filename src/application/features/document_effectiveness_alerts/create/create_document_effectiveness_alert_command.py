from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class CreateDocumentEffectivenessAlertCommand:
    new_document_number: str
    new_document_title: str

    announced_date: date | None
    effective_date: date | None

    affected_document_id: UUID

    note: str | None = None

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.CREATE

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return (
            AuditEntity
            .REGULATORY_DOCUMENT
        )

    @property
    def entity_id(
        self,
    ) -> UUID:
        return self.affected_document_id

    def get_payload(
        self,
    ) -> object:
        return {
            "new_document_number":
                self.new_document_number,
            "new_document_title":
                self.new_document_title,
            "announced_date":
                self.announced_date,
            "effective_date":
                self.effective_date,
            "affected_document_id":
                self.affected_document_id,
            "note":
                self.note,
            "operation":
                "effectiveness_alert_created",
        }