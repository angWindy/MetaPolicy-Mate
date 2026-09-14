"""add document metadata approval permission

Revision ID: 99c2278355b8
Revises: 13a2f34a5d37
Create Date: 2026-08-24 11:59:48.559261
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op


revision: str = "99c2278355b8"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "13a2f34a5d37"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    permission_id = str(uuid4())

    op.execute(
        f"""
        INSERT INTO permissions (
            id,
            code,
            name,
            module,
            description
        )
        VALUES (
            '{permission_id}'::uuid,
            'document.approve',
            'Approve document metadata',
            'document',
            'Permission to approve or reject document metadata'
        )
        ON CONFLICT (code)
        DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO role_permissions (
            role_id,
            permission_id
        )
        SELECT
            r.id,
            p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code = 'ADMIN'
          AND p.code = 'document.approve'
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id
            FROM permissions
            WHERE code = 'document.approve'
        )
        """
    )

    op.execute(
        """
        DELETE FROM permissions
        WHERE code = 'document.approve'
        """
    )