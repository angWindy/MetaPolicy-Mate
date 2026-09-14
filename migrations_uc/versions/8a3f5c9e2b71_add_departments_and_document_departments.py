"""add departments and document_departments tables

Revision ID: 8a3f5c9e2b71
Revises: e12aee307c05
Create Date: 2026-08-23 15:30:00.000000

This migration adds:
1. departments table (master data for organizational units)
2. document_departments join table (many-to-many documents <-> departments)
3. Updates users.department -> users.department_id (FK to departments)

Note: This migration is idempotent - it will skip steps if the schema is already in the target state.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a3f5c9e2b71"
down_revision: Union[str, Sequence[str], None] = "e12aee307c05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add departments and document_departments; align users.department_id."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. Create departments table if it doesn't exist
    if "departments" not in existing_tables:
        op.create_table(
            "departments",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_departments_code"),
        )
        op.create_index("ix_departments_code", "departments", ["code"], unique=True)

    # 2. Create document_departments table if it doesn't exist
    if "document_departments" not in existing_tables:
        op.create_table(
            "document_departments",
            sa.Column("document_id", sa.UUID(), nullable=False),
            sa.Column("department_id", sa.UUID(), nullable=False),
            sa.ForeignKeyConstraint(
                ["department_id"],
                ["departments.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["document_id"],
                ["documents.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("document_id", "department_id"),
        )

    # 3. Align users.department_id with the actual schema (add it if missing)
    users_columns = {c["name"] for c in inspector.get_columns("users")}
    if "department_id" not in users_columns and "department" in users_columns:
        # If old column 'department' exists, rename it via adding the new one
        op.add_column(
            "users",
            sa.Column("department_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            "fk_users_department_id_departments",
            "users",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )
    elif "department_id" not in users_columns:
        op.add_column(
            "users",
            sa.Column("department_id", sa.UUID(), nullable=True),
        )
        op.create_foreign_key(
            "fk_users_department_id_departments",
            "users",
            "departments",
            ["department_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "document_departments" in existing_tables:
        op.drop_table("document_departments")

    users_columns = {c["name"] for c in inspector.get_columns("users")}
    if "department_id" in users_columns:
        op.drop_constraint(
            "fk_users_department_id_departments", "users", type_="foreignkey"
        )
        op.drop_column("users", "department_id")

    if "departments" in existing_tables:
        op.drop_index("ix_departments_code", table_name="departments")
        op.drop_table("departments")
