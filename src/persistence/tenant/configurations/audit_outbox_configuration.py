from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from src.persistence.tenant.database import metadata


audit_outbox = Table(
    "audit_outbox",
    metadata,
    Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
    ),
    Column(
        "event_type",
        String(100),
        nullable=False,
        server_default="audit.event",
    ),
    Column(
        "payload",
        Text,
        nullable=False,
    ),
    Column(
        "status",
        String(50),
        nullable=False,
        server_default="Pending",
    ),
    Column(
        "retry_count",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "processed_at",
        DateTime(timezone=True),
        nullable=True,
    ),
    Column(
        "error",
        Text,
        nullable=True,
    ),
    Index(
        "ix_audit_outbox_status",
        "status",
    ),
    Index(
        "ix_audit_outbox_created_at",
        "created_at",
    ),
)