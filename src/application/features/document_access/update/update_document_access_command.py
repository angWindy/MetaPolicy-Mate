from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)


@dataclass(frozen=True)
class UpdateDocumentAccessCommand:
    document_id: UUID

    access_scope: DocumentAccessScope

    department_ids: list[UUID]

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
                "document_access_updated"
            ),
            "access_scope": (
                self.access_scope.value
            ),
            "department_ids": [
                str(item)
                for item
                in self.department_ids
            ],
        }