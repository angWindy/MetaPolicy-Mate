from sqlalchemy import (
    Boolean,
    Column,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID

from src.persistence.master.database import metadata


schools = Table(
    "Schools",
    metadata,

    Column(
        "Id",
        UUID(as_uuid=True),
        primary_key=True,
    ),

    Column(
        "Code",
        String(50),
        nullable=False,
        unique=True,
    ),

    Column(
        "Name",
        String(255),
        nullable=False,
    ),

    Column(
        "DatabaseUrl",
        String(1000),
        nullable=False,
    ),

    Column(
        "IsActive",
        Boolean,
        nullable=False,
        default=True,
    ),
)