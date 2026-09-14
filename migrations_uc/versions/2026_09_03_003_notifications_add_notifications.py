"""add notifications table

Revision ID: 2026_09_03_003_notifications
Revises: 2026_09_03_002_saved
Create Date: 2026-09-03 16:52:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2026_09_03_003_notifications"
down_revision: Union[str, Sequence[str], None] = "2026_09_03_002_saved"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.String(100),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "related_document_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_document_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_user_id",
        "notifications",
        ["user_id"],
    )
    op.create_index(
        "ix_notifications_is_read",
        "notifications",
        ["is_read"],
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notifications_created_at",
        table_name="notifications",
    )
    op.drop_index(
        "ix_notifications_is_read",
        table_name="notifications",
    )
    op.drop_index(
        "ix_notifications_user_id",
        table_name="notifications",
    )
    op.drop_table("notifications")
