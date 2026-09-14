from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SectionMetadataDraftResponse(
    BaseModel
):
    id: UUID

    document_id: UUID
    version_id: UUID

    section_id: UUID | None
    chunk_id: UUID

    metadata: dict

    cross_references: list[dict]

    needs_human_review: bool

    rationale: str | None

    status: str

    reviewed_by: UUID | None
    reviewed_at: datetime | None

    created_at: datetime
    updated_at: datetime | None