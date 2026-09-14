"""add static threshold scope key

Revision ID: d7e69f610115
Revises: 491b8833a627
Create Date: 2026-08-24 17:49:41.056326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e69f610115'
down_revision: Union[str, Sequence[str], None] = '491b8833a627'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "static_thresholds",
        sa.Column(
            "scope_key",
            sa.String(
                length=200
            ),
            nullable=True,
        ),
    )

    op.execute(
        """
        UPDATE static_thresholds
        SET scope_key =
            'LEGACY-' ||
            md5(
                lower(
                    trim(condition_text)
                )
            )
        WHERE scope_key IS NULL
        """
    )

    op.alter_column(
        "static_thresholds",
        "scope_key",
        existing_type=(
            sa.String(
                length=200
            )
        ),
        nullable=False,
    )

    op.drop_index(
        "uq_static_thresholds_current",
        table_name="static_thresholds",
    )

    op.drop_constraint(
        "uq_static_thresholds_key_version",
        "static_thresholds",
        type_="unique",
    )

    op.create_index(
        "ix_static_thresholds_scope_key",
        "static_thresholds",
        ["scope_key"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_static_thresholds_"
        "key_scope_version",
        "static_thresholds",
        [
            "threshold_key",
            "scope_key",
            "version_number",
        ],
    )

    op.create_index(
        "uq_static_thresholds_"
        "current_scope",
        "static_thresholds",
        [
            "threshold_key",
            "scope_key",
        ],
        unique=True,
        postgresql_where=(
            sa.text(
                "is_current = true"
            )
        ),
    )

def downgrade() -> None:
    op.drop_index(
        "uq_static_thresholds_"
        "current_scope",
        table_name="static_thresholds",
    )

    op.drop_constraint(
        "uq_static_thresholds_"
        "key_scope_version",
        "static_thresholds",
        type_="unique",
    )

    # Old schema chỉ cho phép
    # một current / threshold_key.
    op.execute(
        """
        WITH ranked AS
        (
            SELECT
                id,
                row_number() OVER
                (
                    PARTITION BY threshold_key
                    ORDER BY
                        verified_at DESC
                            NULLS LAST,
                        created_at DESC,
                        id
                ) AS rn
            FROM static_thresholds
            WHERE is_current = true
        )
        UPDATE static_thresholds AS t
        SET is_current = false
        FROM ranked AS r
        WHERE t.id = r.id
          AND r.rn > 1
        """
    )

    # Old schema cũng cần
    # version_number unique / key.
    op.execute(
        """
        WITH ranked AS
        (
            SELECT
                id,
                row_number() OVER
                (
                    PARTITION BY threshold_key
                    ORDER BY
                        version_number,
                        created_at,
                        id
                ) AS new_version
            FROM static_thresholds
        )
        UPDATE static_thresholds AS t
        SET version_number =
            r.new_version
        FROM ranked AS r
        WHERE t.id = r.id
        """
    )

    op.drop_index(
        "ix_static_thresholds_scope_key",
        table_name="static_thresholds",
    )

    op.drop_column(
        "static_thresholds",
        "scope_key",
    )

    op.create_unique_constraint(
        "uq_static_thresholds_key_version",
        "static_thresholds",
        [
            "threshold_key",
            "version_number",
        ],
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