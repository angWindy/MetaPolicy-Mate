"""Add ``is_admin`` column to public.users.

Why
----
Previously every authenticated user was scoped to their own
``department_id`` for document access. The demo admin user was
attached to the HUST department, so admin logins only saw HUST
documents. This migration adds an ``is_admin`` boolean so the
document access policy can bypass the per-school filter for
legitimate admins while still letting them be a member of a
department (so the JWT carries a real ``school_code`` for things
like object keys in R2).

The column is added with a default of FALSE so the migration is
safe to run on existing data; the ``scripts/seed_uc_demo.py`` and
``scripts/seed_docker_db.py`` updates set the flag to TRUE for
``admin@p234.demo`` and ``crossschool@p234.demo`` on their next
seed/reset.

Revision ID: 0051_add_users_is_admin
Revises: 0050_add_documents_school_id
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0051_add_users_is_admin"
down_revision = "6da4faf00aaa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
