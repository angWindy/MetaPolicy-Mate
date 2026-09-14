from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)
from src.domain.enums.document_reference_nature import (
    DocumentReferenceNature,
)


@dataclass(frozen=True)
class CreateDocumentApplicationScopeCommand:
    source_document_id: UUID
    related_document_id: UUID

    scope_type: ApplicationScopeType
    scope_detail: str | None

    reference_nature: (
        DocumentReferenceNature
    )

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
        return self.source_document_id

    def get_payload(
        self,
    ) -> object:
        return {
            "operation":
                "document_application_scope_created",

            "source_document_id":
                self.source_document_id,

            "related_document_id":
                self.related_document_id,

            "scope_type":
                self.scope_type.value,

            "scope_detail":
                self.scope_detail,

            "reference_nature":
                self.reference_nature.value,
        }