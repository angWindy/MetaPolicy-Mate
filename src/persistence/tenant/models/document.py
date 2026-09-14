from datetime import (
    date,
    datetime,
)
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    String,
    func,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import Base


class DocumentModel(
    Base
):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    document_number: Mapped[
        str
    ] = mapped_column(
        String(100),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    issued_by: Mapped[
        str
    ] = mapped_column(
        String(255),
        nullable=False,
    )

    issued_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
    )

    effective_date: Mapped[
        date
    ] = mapped_column(
        Date,
        nullable=False,
    )

    legal_status: Mapped[
        str
    ] = mapped_column(
        String(50),
        nullable=False,
    )

    access_scope: Mapped[
        str
    ] = mapped_column(
        String(50),
        nullable=False,
        default="PUBLIC",
        server_default="PUBLIC",
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "uq_documents_document_number_ci",
            func.lower(
                document_number
            ),
            unique=True,
        ),

        Index(
            "ix_documents_document_number",
            "document_number",
        ),

        Index(
            "ix_documents_legal_status",
            "legal_status",
        ),

        Index(
            "ix_documents_issued_date",
            "issued_date",
        ),

        Index(
            "ix_documents_access_scope",
            "access_scope",
        ),
    )