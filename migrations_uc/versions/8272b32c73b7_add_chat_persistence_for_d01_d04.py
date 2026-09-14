"""add chat persistence for D01 D04

Revision ID: 8272b32c73b7
Revises: e1644246e6c1
Create Date: 2026-08-25 11:16:21.181333

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8272b32c73b7'
down_revision: Union[str, Sequence[str], None] = 'e1644246e6c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
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
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_chat_sessions_user_id",
        "chat_sessions",
        ["user_id"],
    )

    op.create_index(
        "ix_chat_sessions_updated_at",
        "chat_sessions",
        ["updated_at"],
    )

    op.create_table(
        "chat_turns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "question",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "answer",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "citations",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_chat_turns_session_id",
        "chat_turns",
        ["session_id"],
    )

    op.create_index(
        "ix_chat_turns_created_at",
        "chat_turns",
        ["created_at"],
    )

def downgrade() -> None:
    op.drop_index(
        "ix_chat_turns_created_at",
        table_name="chat_turns",
    )
    op.drop_index(
        "ix_chat_turns_session_id",
        table_name="chat_turns",
    )
    op.drop_table("chat_turns")

    op.drop_index(
        "ix_chat_sessions_updated_at",
        table_name="chat_sessions",
    )
    op.drop_index(
        "ix_chat_sessions_user_id",
        table_name="chat_sessions",
    )
    op.drop_table("chat_sessions")
