from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)


@dataclass
class DocumentVersion:
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

    replaces_version_id: (
        UUID | None
    ) = None

    created_at: (
        datetime | None
    ) = None

    # Review metadata (Phase 3b)
    review_notes: str | None = None
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None