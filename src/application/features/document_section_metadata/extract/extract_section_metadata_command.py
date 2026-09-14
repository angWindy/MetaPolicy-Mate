from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class ExtractSectionMetadataCommand:
    document_id: UUID
    version_id: UUID

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
        return self.document_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation": (
                "section_metadata_extracted"
            ),
            "document_id": (
                self.document_id
            ),
            "version_id": (
                self.version_id
            ),
        }