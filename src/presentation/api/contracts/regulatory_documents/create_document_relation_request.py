from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)


class CreateDocumentRelationRequest(
    BaseModel
):
    target_document_id: UUID

    relation_type: DocumentRelationType

    note: str | None = None

    confirm_conflict: bool = False