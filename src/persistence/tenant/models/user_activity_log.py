from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import Base


class UserActivityLogModel(Base):
    __tablename__ = (
        "user_activity_logs"
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )

    school_id: Mapped[
        UUID | None
    ] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    user_id: Mapped[
        UUID | None
    ] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    request_name: Mapped[
        str
    ] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    status: Mapped[
        str
    ] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    trace_id: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    ip_address: Mapped[
        str | None
    ] = mapped_column(
        String(100),
        nullable=True,
    )

    device_id: Mapped[
        str | None
    ] = mapped_column(
        String(255),
        nullable=True,
    )

    user_agent: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    completed_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )