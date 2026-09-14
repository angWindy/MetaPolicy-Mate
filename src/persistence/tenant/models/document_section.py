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


class DocumentSectionModel(
    Base
):
    __tablename__ = (
        "document_sections"
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

    section_type: Mapped[
        str | None
    ] = mapped_column(
        String(30),
        nullable=True,
    )

    section_number: Mapped[
        str | None
    ] = mapped_column(
        String(50),
        nullable=True,
    )

    heading: Mapped[
        str | None
    ] = mapped_column(
        String(1000),
        nullable=True,
    )

    heading_path: Mapped[
        list[str]
    ] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    page: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    sort_order: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )