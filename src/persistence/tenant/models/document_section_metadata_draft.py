from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import (
    JSONB,
    UUID as PGUUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import (
    Base,
)


class DocumentSectionMetadataDraftModel(
    Base
):
    __tablename__ = (
        "document_section_metadata_drafts"
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    document_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    version_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    section_id: Mapped[
        UUID | None
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_sections.id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    chunk_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_chunks.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    metadata_json: Mapped[
        dict
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text(
            "'{}'::jsonb"
        ),
    )

    cross_references_json: Mapped[
        list
    ] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text(
            "'[]'::jsonb"
        ),
    )

    needs_human_review: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text(
            "true"
        ),
    )

    rationale: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[
        str
    ] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    reviewed_by: Mapped[
        UUID | None
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    reviewed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            name=(
                "uq_section_metadata_"
                "draft_chunk"
            ),
        ),
    )