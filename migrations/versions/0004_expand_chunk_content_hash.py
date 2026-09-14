"""Expand chunks.content_hash for algorithm-qualified SHA-256 values."""

import sqlalchemy as sa
from alembic import op

revision = "0004_expand_chunk_content_hash"
down_revision = "0003_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]: column
        for column in sa.inspect(op.get_bind()).get_columns("chunks")
    }
    existing = columns.get("content_hash")
    if existing is None:
        op.add_column(
            "chunks",
            sa.Column("content_hash", sa.String(length=71), nullable=True),
        )
        return
    if getattr(existing["type"], "length", None) != 71:
        op.alter_column(
            "chunks",
            "content_hash",
            existing_type=existing["type"],
            type_=sa.String(length=71),
            existing_nullable=existing["nullable"],
        )


def downgrade() -> None:
    op.drop_column("chunks", "content_hash")
