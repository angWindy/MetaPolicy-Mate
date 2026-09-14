from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)


@dataclass
class DocumentRelation:
    id: UUID

    source_document_id: UUID
    target_document_id: UUID

    relation_type: DocumentRelationType

    note: str | None = None

    created_at: datetime | None = None