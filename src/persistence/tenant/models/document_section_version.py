from datetime import (
    date,
    datetime,
)
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
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


class DocumentSectionVersionModel(
    Base
):
    __tablename__ = (
        "document_section_versions"
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    section_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_sections.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    version_number: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    effective_from: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
    )

    effective_to: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    is_current: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
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
            "section_id",
            "version_number",
            name=(
                "uq_document_section_versions_"
                "section_version"
            ),
        ),
        Index(
            "uq_document_section_versions_current",
            "section_id",
            unique=True,
            postgresql_where=text(
                "is_current = true"
            ),
        ),
    )