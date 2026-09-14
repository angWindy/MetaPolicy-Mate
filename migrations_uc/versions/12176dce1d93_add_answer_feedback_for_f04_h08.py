"""add answer feedback for F04 H08

Revision ID: 12176dce1d93
Revises: 8272b32c73b7
Create Date: 2026-08-25 12:17:00.154541

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import (
    postgresql,
)

# revision identifiers, used by Alembic.
revision: str = '12176dce1d93'
down_revision: Union[str, Sequence[str], None] = '8272b32c73b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "answer_feedbacks",
        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),
        sa.Column(
            "reported_by_user_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),
        sa.Column(
            "feedback_type",
            sa.String(30),
            nullable=False,
        ),
        sa.Column(
            "comment",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
        ),
        sa.Column(
            "review_result",
            sa.String(30),
            nullable=True,
        ),
        sa.Column(
            "review_note",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
        ),
        sa.Column(
            "reviewed_by_user_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["chat_turns.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reported_by_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "id"
        ),
    )

    op.create_index(
        "ix_answer_feedbacks_turn_id",
        "answer_feedbacks",
        ["turn_id"],
    )

    op.create_index(
        "ix_answer_feedbacks_reported_by_user_id",
        "answer_feedbacks",
        ["reported_by_user_id"],
    )

    op.create_index(
        "ix_answer_feedbacks_status",
        "answer_feedbacks",
        ["status"],
    )

    op.create_index(
        "ix_answer_feedbacks_review_result",
        "answer_feedbacks",
        ["review_result"],
    )

    op.create_index(
        "ix_answer_feedbacks_created_at",
        "answer_feedbacks",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_answer_feedbacks_created_at",
        table_name="answer_feedbacks",
    )

    op.drop_index(
        "ix_answer_feedbacks_review_result",
        table_name="answer_feedbacks",
    )

    op.drop_index(
        "ix_answer_feedbacks_status",
        table_name="answer_feedbacks",
    )

    op.drop_index(
        "ix_answer_feedbacks_reported_by_user_id",
        table_name="answer_feedbacks",
    )

    op.drop_index(
        "ix_answer_feedbacks_turn_id",
        table_name="answer_feedbacks",
    )

    op.drop_table(
        "answer_feedbacks"
    )