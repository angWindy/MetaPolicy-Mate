from uuid import UUID

from sqlalchemy import (
    ForeignKey,
    PrimaryKeyConstraint,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PGUUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import Base


class DocumentDepartmentModel(
    Base
):
    __tablename__ = (
        "document_departments"
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
    )

    department_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "departments.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "document_id",
            "department_id",
            name=(
                "pk_document_departments"
            ),
        ),
    )