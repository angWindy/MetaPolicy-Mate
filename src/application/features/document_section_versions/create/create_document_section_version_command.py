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
class CreateDocumentSectionVersionCommand:
    section_id: UUID

    content: str

    effective_from: date
    effective_to: date | None

    is_current: bool

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
        return self.section_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "document_section_"
                "version_created"
            ),
            "section_id": (
                self.section_id
            ),
            "effective_from": (
                self.effective_from
            ),
            "effective_to": (
                self.effective_to
            ),
            "is_current": (
                self.is_current
            ),
        }