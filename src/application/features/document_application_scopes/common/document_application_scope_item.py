from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.document_application_scope import (
    DocumentApplicationScope,
)
from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.enums.document_reference_nature import (
    DocumentReferenceNature,
)


@dataclass(frozen=True)
class DocumentApplicationScopeItem:
    id: UUID

    source_document_id: UUID
    source_version_id: UUID

    related_document_id: UUID

    scope_type: ApplicationScopeType
    scope_detail: str | None

    reference_nature: (
        DocumentReferenceNature
    )

    created_by: UUID | None
    created_at: datetime

    @staticmethod
    def from_entity(
        entity: DocumentApplicationScope,
    ) -> "DocumentApplicationScopeItem":
        return DocumentApplicationScopeItem(
            id=entity.id,
            source_document_id=(
                entity.source_document_id
            ),
            source_version_id=(
                entity.source_version_id
            ),
            related_document_id=(
                entity.related_document_id
            ),
            scope_type=(
                entity.scope_type
            ),
            scope_detail=(
                entity.scope_detail
            ),
            reference_nature=(
                entity.reference_nature
            ),
            created_by=(
                entity.created_by
            ),
            created_at=(
                entity.created_at
            ),
        )