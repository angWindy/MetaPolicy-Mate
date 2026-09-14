from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class ApproveSectionMetadataCommand:
    draft_id: UUID

    reviewer_user_id: UUID

    metadata: dict

    cross_references: list[dict]

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
                "section_metadata_approved"
            ),
            "draft_id": (
                self.draft_id
            ),
        }