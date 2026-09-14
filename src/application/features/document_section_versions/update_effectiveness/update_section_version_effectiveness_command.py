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
class UpdateSectionVersionEffectivenessCommand:
    section_id: UUID
    version_id: UUID

    effective_from: date
    effective_to: date | None

    is_current: bool

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.UPDATE

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
                "document_section_version_"
                "effectiveness_updated"
            ),
            "section_id": (
                self.section_id
            ),
            "version_id": (
                self.version_id
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