"""add user activity logs

Revision ID: e12aee307c05
Revises: b7168579e73d
Create Date: 2026-08-22 09:52:59.949960

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e12aee307c05'
down_revision: Union[str, Sequence[str], None] = 'b7168579e73d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_activity_logs",

        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "school_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),

        sa.Column(
            "user_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),

        sa.Column(
            "request_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "trace_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "ip_address",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "device_id",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "user_agent",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )

    op.create_index(
        "ix_user_activity_logs_school_id",
        "user_activity_logs",
        ["school_id"],
    )

    op.create_index(
        "ix_user_activity_logs_user_id",
        "user_activity_logs",
        ["user_id"],
    )

    op.create_index(
        "ix_user_activity_logs_trace_id",
        "user_activity_logs",
        ["trace_id"],
    )

    op.create_index(
        "ix_user_activity_logs_request_name",
        "user_activity_logs",
        ["request_name"],
    )

    op.create_index(
        "ix_user_activity_logs_started_at",
        "user_activity_logs",
        ["started_at"],
    )

    op.add_column(
        "audit_logs",
        sa.Column(
            "trace_id",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_audit_logs_trace_id",
        "audit_logs",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_audit_logs_trace_id",
        table_name="audit_logs",
    )

    op.drop_column(
        "audit_logs",
        "trace_id",
    )

    op.drop_index(
        "ix_user_activity_logs_started_at",
        table_name="user_activity_logs",
    )

    op.drop_index(
        "ix_user_activity_logs_request_name",
        table_name="user_activity_logs",
    )

    op.drop_index(
        "ix_user_activity_logs_trace_id",
        table_name="user_activity_logs",
    )

    op.drop_index(
        "ix_user_activity_logs_user_id",
        table_name="user_activity_logs",
    )

    op.drop_index(
        "ix_user_activity_logs_school_id",
        table_name="user_activity_logs",
    )

    op.drop_table(
        "user_activity_logs"
    )
