"""add document section versions for A04

Revision ID: b325a2bca184
Revises: 99c2278355b8
Create Date: 2026-08-24 12:35:05.221604

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import (
    postgresql,
)


# revision identifiers, used by Alembic.
revision: str = 'b325a2bca184'
down_revision: Union[str, Sequence[str], None] = '99c2278355b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "document_section_versions",

        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "section_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "effective_from",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "effective_to",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "is_current",
            sa.Boolean(),
            server_default=(
                sa.text("false")
            ),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            server_default=(
                sa.func.now()
            ),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "section_id",
            "version_number",
            name=(
                "uq_document_section_versions_"
                "section_version"
            ),
        ),
    )

    op.create_index(
        op.f(
            "ix_document_section_versions_"
            "section_id"
        ),
        "document_section_versions",
        ["section_id"],
        unique=False,
    )

    op.create_index(
        "uq_document_section_versions_current",
        "document_section_versions",
        ["section_id"],
        unique=True,
        postgresql_where=(
            sa.text(
                "is_current = true"
            )
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_document_section_versions_current",
        table_name=(
            "document_section_versions"
        ),
    )

    op.drop_index(
        op.f(
            "ix_document_section_versions_"
            "section_id"
        ),
        table_name=(
            "document_section_versions"
        ),
    )

    op.drop_table(
        "document_section_versions"
    )
