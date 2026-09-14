"""add documents access_scope column

Revision ID: 6da4faf00aaa
Revises: 931b75fac2dd
Create Date: 2026-08-31 01:33:21.891212

The ORM model ``DocumentModel.access_scope`` (canonical per AGENTS.md)
expects a ``public.documents.access_scope`` column but the original A0-01
``documents`` migration did not include it. This migration adds the
column with a PUBLIC default so existing rows are still valid.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6da4faf00aaa'
down_revision: Union[str, Sequence[str], None] = '931b75fac2dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "access_scope",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'PUBLIC'"),
        ),
    )
    op.create_index(
        "ix_documents_access_scope",
        "documents",
        ["access_scope"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_access_scope",
        table_name="documents",
    )
    op.drop_column(
        "documents",
        "access_scope",
    )
