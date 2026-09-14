from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class RejectSectionMetadataCommand:
    draft_id: UUID

    reviewer_user_id: UUID

    reason: str

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
        return self.draft_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "section_metadata_rejected"
            ),
            "draft_id": (
                self.draft_id
            ),
            "reason": self.reason,
        }