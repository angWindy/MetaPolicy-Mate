from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity
from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)


@dataclass(frozen=True)
class CreateDocumentRelationCommand:
    source_document_id: UUID
    target_document_id: UUID

    relation_type: DocumentRelationType

    note: str | None = None

    confirm_conflict: bool = False

    @property
    def action(self) -> AuditAction:
        return AuditAction.UPDATE

    @property
    def entity(self) -> AuditEntity:
        return AuditEntity.REGULATORY_DOCUMENT

    @property
    def entity_id(self) -> UUID:
        return self.source_document_id