from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import (
    Base,
)


class DocumentVersionModel(Base):
    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    processing_status: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
        )
    )

    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    source_filename: Mapped[str] = (
        mapped_column(
            String(255),
            nullable=False,
        )
    )

    object_key: Mapped[str] = (
        mapped_column(
            String(1000),
            nullable=False,
        )
    )

    content_type: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
        )
    )

    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    replaces_version_id: Mapped[
        UUID | None
    ] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = (
        mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        )
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name=(
                "uq_document_versions_"
                "document_version"
            ),
        ),
    )