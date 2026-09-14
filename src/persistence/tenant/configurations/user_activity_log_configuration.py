from sqlalchemy import (
    Column,
    DateTime,
    Index,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from src.persistence.tenant.database import metadata


user_activity_logs = Table(
    "user_activity_logs",
    metadata,

    Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
    ),

    Column(
        "school_id",
        UUID(as_uuid=True),
        nullable=True,
    ),

    Column(
        "user_id",
        UUID(as_uuid=True),
        nullable=True,
    ),

    Column(
        "request_name",
        String(255),
        nullable=False,
    ),

    Column(
        "status",
        String(50),
        nullable=False,
    ),

    Column(
        "trace_id",
        String(100),
        nullable=True,
    ),

    Column(
        "ip_address",
        String(50),
        nullable=True,
    ),

    Column(
        "device_id",
        String(100),
        nullable=True,
    ),

    Column(
        "user_agent",
        String(500),
        nullable=True,
    ),

    Column(
        "error_message",
        Text,
        nullable=True,
    ),

    Column(
        "started_at",
        DateTime(timezone=True),
        nullable=False,
    ),

    Column(
        "completed_at",
        DateTime(timezone=True),
        nullable=False,
    ),

    Index(
        "ix_user_activity_logs_school_id",
        "school_id",
    ),

    Index(
        "ix_user_activity_logs_user_id",
        "user_id",
    ),

    Index(
        "ix_user_activity_logs_trace_id",
        "trace_id",
    ),

    Index(
        "ix_user_activity_logs_request_name",
        "request_name",
    ),

    Index(
        "ix_user_activity_logs_started_at",
        "started_at",
    ),
)