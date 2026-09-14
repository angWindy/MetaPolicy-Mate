from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class CreateStaticThresholdCommand:
    threshold_key: str
    scope_key: str

    name: str

    operator: str
    value: Decimal

    unit: str | None

    condition_text: str

    section_id: UUID
    section_version_id: UUID

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
                "static_threshold_created"
            ),
            "threshold_key": (
                self.threshold_key
            ),
            "scope_key": (
                self.scope_key
            ),
            "section_id": (
                self.section_id
            ),
            "section_version_id": (
                self.section_version_id
            ),
        }