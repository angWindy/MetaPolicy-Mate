"""add rbac management permission

Revision ID: b7168579e73d
Revises: 93e869cc0047
"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "b7168579e73d"
down_revision: Union[str, Sequence[str], None] = "93e869cc0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    permission_id = str(uuid4())

    connection.execute(
        sa.text(
            """
            INSERT INTO permissions
            (
                id,
                code,
                name,
                module,
                description
            )
            SELECT
                CAST(:id AS uuid),
                'rbac.manage',
                'Manage RBAC',
                'rbac',
                'Assign roles and permissions'
            WHERE NOT EXISTS
            (
                SELECT 1
                FROM permissions
                WHERE code = 'rbac.manage'
            )
            """
        ),
        {
            "id": permission_id,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions
            (
                role_id,
                permission_id
            )
            SELECT
                r.id,
                p.id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.code = 'ADMIN'
              AND p.code = 'rbac.manage'
              AND NOT EXISTS
              (
                  SELECT 1
                  FROM role_permissions rp
                  WHERE rp.role_id = r.id
                    AND rp.permission_id = p.id
              )
            """
        )
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id IN
            (
                SELECT id
                FROM permissions
                WHERE code = 'rbac.manage'
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code = 'rbac.manage'
            """
        )
    )