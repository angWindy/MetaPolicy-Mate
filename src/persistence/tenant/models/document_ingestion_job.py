from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
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


class DocumentIngestionJobModel(
    Base
):
    __tablename__ = (
        "document_ingestion_jobs"
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

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    warnings: Mapped[
        list
    ] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    section_count: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    chunk_count: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    started_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )