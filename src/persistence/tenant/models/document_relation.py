from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
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


class DocumentRelationModel(Base):
    __tablename__ = "document_relations"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    source_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    target_document_id: Mapped[UUID] = mapped_column(
        ForeignKey(
            "documents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    relation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    note: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            name=(
                "uq_document_relations_"
                "source_target_type"
            ),
        ),
    )