"""add static thresholds for A05

Revision ID: b53437b71ffb
Revises: b325a2bca184
Create Date: 2026-08-24 14:27:19.722991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b53437b71ffb'
down_revision: Union[str, Sequence[str], None] = 'b325a2bca184'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "static_thresholds",

        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "threshold_key",
            sa.String(
                length=150
            ),
            nullable=False,
        ),

        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "name",
            sa.String(
                length=500
            ),
            nullable=False,
        ),

        sa.Column(
            "operator",
            sa.String(
                length=10
            ),
            nullable=False,
        ),

        sa.Column(
            "value",
            sa.Numeric(
                precision=18,
                scale=4,
            ),
            nullable=False,
        ),

        sa.Column(
            "unit",
            sa.String(
                length=100
            ),
            nullable=True,
        ),

        sa.Column(
            "condition_text",
            sa.Text(),
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
            "section_version_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.String(
                length=30
            ),
            server_default=(
                sa.text("'DRAFT'")
            ),
            nullable=False,
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
            "verified_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
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
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["section_version_id"],
            [
                "document_section_versions.id"
            ],
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "threshold_key",
            "version_number",
            name=(
                "uq_static_thresholds_"
                "key_version"
            ),
        ),
    )

    op.create_index(
        op.f(
            "ix_static_thresholds_"
            "threshold_key"
        ),
        "static_thresholds",
        ["threshold_key"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_static_thresholds_"
            "section_id"
        ),
        "static_thresholds",
        ["section_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_static_thresholds_"
            "section_version_id"
        ),
        "static_thresholds",
        ["section_version_id"],
        unique=False,
    )

    op.create_index(
        "uq_static_thresholds_current",
        "static_thresholds",
        ["threshold_key"],
        unique=True,
        postgresql_where=(
            sa.text(
                "is_current = true"
            )
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_static_thresholds_current",
        table_name="static_thresholds",
    )

    op.drop_index(
        op.f(
            "ix_static_thresholds_"
            "section_version_id"
        ),
        table_name="static_thresholds",
    )

    op.drop_index(
        op.f(
            "ix_static_thresholds_"
            "section_id"
        ),
        table_name="static_thresholds",
    )

    op.drop_index(
        op.f(
            "ix_static_thresholds_"
            "threshold_key"
        ),
        table_name="static_thresholds",
    )

    op.drop_table(
        "static_thresholds"
    )