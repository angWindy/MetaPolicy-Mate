from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Date,
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


class DocumentEffectivenessAlertModel(
    Base
):
    __tablename__ = (
        "document_effectiveness_alerts"
    )

    id: Mapped[UUID] = (
        mapped_column(
            primary_key=True
        )
    )

    new_document_number: Mapped[str] = (
        mapped_column(
            String(100),
            nullable=False,
        )
    )

    new_document_title: Mapped[str] = (
        mapped_column(
            String(500),
            nullable=False,
        )
    )

    announced_date: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    effective_date: Mapped[
        date | None
    ] = mapped_column(
        Date,
        nullable=True,
    )

    affected_document_id: Mapped[
        UUID
    ] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = (
        mapped_column(
            String(30),
            nullable=False,
        )
    )

    note: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
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

    updated_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(
            timezone=True
        ),
        nullable=True,
    )