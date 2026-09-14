from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PGUUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import (
    Base,
)


class DocumentChunkModel(
    Base
):
    __tablename__ = (
        "document_chunks"
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
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
            ondelete="SET NULL",
        ),

        nullable=True,
        index=True,
    )

    chunk_index: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    embedding_text: Mapped[
        str
    ] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[
        str
    ] = mapped_column(
        String(64),
        nullable=False,
    )

    metadata_json: Mapped[
        dict
    ] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )