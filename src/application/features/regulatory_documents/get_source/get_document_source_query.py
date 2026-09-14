from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity


@dataclass(frozen=True)
class GetDocumentSourceQuery:
    document_id: UUID

    @property
    def action(self) -> AuditAction:
        return AuditAction.READ

    @property
    def entity(self) -> AuditEntity:
        return AuditEntity.REGULATORY_DOCUMENT

    @property
    def entity_id(self):
        return str(self.document_id)

    def get_payload(self) -> object:
        return {
            "document_id": str(self.document_id),
        }
