from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity


@dataclass(frozen=True)
class ReplaceDocumentSourceCommand:
    document_id: UUID

    source_filename: str
    content_type: str
    content: bytes

    @property
    def action(self) -> AuditAction:
        return AuditAction.UPDATE

    @property
    def entity(self) -> AuditEntity:
        return AuditEntity.REGULATORY_DOCUMENT

    @property
    def entity_id(self) -> UUID:
        return self.document_id

    def get_payload(self) -> object:
        return {
            "document_id": self.document_id,
            "source_filename": self.source_filename,
            "content_type": self.content_type,
            "size_bytes": len(self.content),
        }