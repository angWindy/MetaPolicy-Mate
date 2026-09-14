"""Add documents.school_id for tenant scoping.

The clean-arch document upload handler already stamps ``school_id`` from
the JWT into the storage ``object_key``. This revision promotes that
information into a first-class column so list/get/delete endpoints can
filter rows by tenant and reject cross-school access attempts.

Revision ID: 0050_add_documents_school_id
Revises: cc0902b4e6c6
Create Date: 2026-08-24 19:30:00.000000
"""
import sqlalchemy as sa
from alembic import op


revision = "0050_add_documents_school_id"
down_revision = "cc0902b4e6c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {
        column["name"]
        for column in inspector.get_columns("documents")
    }
    if "school_id" not in existing:
        op.add_column(
            "documents",
            sa.Column(
                "school_id",
                sa.dialects.postgresql.UUID(),
                nullable=True,
            ),
        )
    existing_indexes = {
        index["name"]
        for index in inspector.get_indexes("documents")
    }
    if "ix_documents_school_id" not in existing_indexes:
        op.create_index(
            "ix_documents_school_id",
            "documents",
            ["school_id"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_school_id",
        table_name="documents",
    )
    op.drop_column(
        "documents",
        "school_id",
    )