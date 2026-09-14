"""add review columns to document_versions (Phase 3b)

Revision ID: 2026_09_03_004_review
Revises: 2026_09_03_003_notifications
Create Date: 2026-09-03 16:55:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2026_09_03_004_review"
down_revision: Union[str, Sequence[str], None] = "2026_09_03_003_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("review_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "document_versions",
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_document_versions_reviewed_by",
        "document_versions",
        "users",
        ["reviewed_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_document_versions_reviewed_by",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_column("document_versions", "reviewed_at")
    op.drop_column("document_versions", "reviewed_by")
    op.drop_column("document_versions", "review_notes")
