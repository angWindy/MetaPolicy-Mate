from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.document_section_metadata_draft import (
    DocumentSectionMetadataDraft,
)


@dataclass(frozen=True)
class SectionMetadataDraftItem:
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

    @classmethod
    def from_entity(
        cls,
        entity: (
            DocumentSectionMetadataDraft
        ),
    ) -> "SectionMetadataDraftItem":
        return cls(
            id=entity.id,
            document_id=(
                entity.document_id
            ),
            version_id=(
                entity.version_id
            ),
            section_id=(
                entity.section_id
            ),
            chunk_id=(
                entity.chunk_id
            ),
            metadata=dict(
                entity.metadata
            ),
            cross_references=[
                dict(item)
                for item
                in entity.cross_references
            ],
            needs_human_review=(
                entity.needs_human_review
            ),
            rationale=(
                entity.rationale
            ),
            status=entity.status.value,
            reviewed_by=(
                entity.reviewed_by
            ),
            reviewed_at=(
                entity.reviewed_at
            ),
            created_at=(
                entity.created_at
            ),
            updated_at=(
                entity.updated_at
            ),
        )