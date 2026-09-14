from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)


class DocumentVersionResponse(
    BaseModel
):
    id: UUID
    document_id: UUID
    version_number: int

    processing_status: (
        DocumentProcessingStatus
    )

    checksum: str
    source_filename: str
    object_key: str
    content_type: str
    size_bytes: int

    replaces_version_id: UUID | None

    created_at: datetime | None