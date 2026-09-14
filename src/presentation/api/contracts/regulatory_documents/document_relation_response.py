from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)


class DocumentRelationResponse(
    BaseModel
):
    id: UUID

    source_document_id: UUID
    target_document_id: UUID

    relation_type: DocumentRelationType

    note: str | None

    created_at: datetime | None