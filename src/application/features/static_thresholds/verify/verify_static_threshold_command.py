from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class VerifyStaticThresholdCommand:
    threshold_id: UUID

    confirm_replacement: bool = False

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
        return self.threshold_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "static_threshold_verified"
            ),

            "threshold_id": (
                self.threshold_id
            ),

            "confirm_replacement": (
                self.confirm_replacement
            ),
        }