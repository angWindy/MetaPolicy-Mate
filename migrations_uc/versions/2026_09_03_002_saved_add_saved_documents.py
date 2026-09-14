"""add saved_documents for user bookmarks

Revision ID: 2026_09_03_002_saved
Revises: 0051_add_users_is_admin
Create Date: 2026-09-03 16:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2026_09_03_002_saved"
down_revision: Union[str, Sequence[str], None] = "0051_add_users_is_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "saved_documents",
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
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "document_id",
            name="uq_saved_documents_user_document",
        ),
    )
    op.create_index(
        "ix_saved_documents_user_id",
        "saved_documents",
        ["user_id"],
    )
    op.create_index(
        "ix_saved_documents_document_id",
        "saved_documents",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_saved_documents_document_id",
        table_name="saved_documents",
    )
    op.drop_index(
        "ix_saved_documents_user_id",
        table_name="saved_documents",
    )
    op.drop_table("saved_documents")
