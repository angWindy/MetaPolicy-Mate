from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)


class DocumentVersionSummary(BaseModel):
    """Lightweight view of a document version for admin tooling."""

    id: UUID
    document_id: UUID
    version_number: int
    processing_status: DocumentProcessingStatus
    source_filename: str
    size_bytes: int
    object_key: str
    created_at: datetime | None
