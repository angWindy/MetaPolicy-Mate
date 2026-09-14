from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
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


class StaticThresholdModel(
    Base
):
    __tablename__ = "static_thresholds"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    threshold_key: Mapped[
        str
    ] = mapped_column(
        String(150),
        nullable=False,
        index=True,
    )

    scope_key: Mapped[
        str
    ] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    version_number: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    operator: Mapped[
        str
    ] = mapped_column(
        String(10),
        nullable=False,
    )

    value: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(
            precision=18,
            scale=4,
        ),
        nullable=False,
    )

    unit: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )

    condition_text: Mapped[
        str
    ] = mapped_column(
        Text,
        nullable=False,
    )

    section_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_sections.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    section_version_id: Mapped[
        UUID
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "document_section_versions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[
        str
    ] = mapped_column(
        String(30),
        nullable=False,
        server_default=text(
            "'DRAFT'"
        ),
    )

    is_current: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text(
            "false"
        ),
    )

    verified_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
            "threshold_key",
            "scope_key",
            "version_number",
            name=(
                "uq_static_thresholds_"
                "key_scope_version"
            ),
        ),
        Index(
            "uq_static_thresholds_"
            "current_scope",
            "threshold_key",
            "scope_key",
            unique=True,
            postgresql_where=text(
                "is_current = true"
            ),
        ),
    )