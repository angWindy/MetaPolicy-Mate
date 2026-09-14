from datetime import datetime
from uuid import (
    UUID,
    uuid4,
)

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PGUUID,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from src.persistence.tenant.database import Base


class UserModel(
    Base
):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash: Mapped[
        str
    ] = mapped_column(
        String(500),
        nullable=False,
    )

    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    department_id: Mapped[
        UUID | None
    ] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "departments.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    token_version: Mapped[
        int
    ] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    is_active: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    is_admin: Mapped[
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
        server_default=text(
            "CURRENT_TIMESTAMP"
        ),
    )

    updated_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )