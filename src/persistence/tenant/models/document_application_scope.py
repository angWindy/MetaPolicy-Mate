from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import (
    Base,
)


class DocumentApplicationScopeModel(
    Base
):
    __tablename__ = (
        "document_application_scopes"
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    source_document_id: Mapped[
        UUID
    ] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    source_version_id: Mapped[
        UUID
    ] = mapped_column(
        ForeignKey(
            "document_versions.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    related_document_id: Mapped[
        UUID
    ] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    scope_type: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
        )
    )

    scope_detail: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    reference_nature: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
        )
    )

    created_by: Mapped[
        UUID | None
    ] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(
            timezone=True
        ),
        nullable=False,
    )