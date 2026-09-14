"""add audit and activity log read permissions

Revision ID: e1644246e6c1
Revises: d7e69f610115
Create Date: 2026-08-24 17:50:29.683277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from uuid import uuid4

# revision identifiers, used by Alembic.
revision: str = 'e1644246e6c1'
down_revision: Union[str, Sequence[str], None] = 'd7e69f610115'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    audit_permission_id = str(
        uuid4()
    )

    activity_permission_id = str(
        uuid4()
    )

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
                'document.audit.read',
                'Read document audit history',
                'document',
                'View document changelog and audit history'
            WHERE NOT EXISTS
            (
                SELECT 1
                FROM permissions
                WHERE code =
                    'document.audit.read'
            )
            """
        ),
        {
            "id":
                audit_permission_id,
        },
    )

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
                'activity_log.read',
                'Read activity logs',
                'activity_log',
                'View user activity logs'
            WHERE NOT EXISTS
            (
                SELECT 1
                FROM permissions
                WHERE code =
                    'activity_log.read'
            )
            """
        ),
        {
            "id":
                activity_permission_id,
        },
    )

    # Admin được xem changelog.
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
              AND p.code =
                  'document.audit.read'
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

    # Các role chuyên gia đang có
    # document.approve cũng được xem.
    connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions
            (
                role_id,
                permission_id
            )
            SELECT
                existing.role_id,
                audit_permission.id
            FROM role_permissions existing
            JOIN permissions approve_permission
              ON approve_permission.id =
                 existing.permission_id
            CROSS JOIN permissions audit_permission
            WHERE approve_permission.code =
                    'document.approve'
              AND audit_permission.code =
                    'document.audit.read'
              AND NOT EXISTS
              (
                  SELECT 1
                  FROM role_permissions rp
                  WHERE rp.role_id =
                        existing.role_id
                    AND rp.permission_id =
                        audit_permission.id
              )
            """
        )
    )

    # Activity log chỉ Admin.
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
              AND p.code =
                  'activity_log.read'
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
                WHERE code IN
                (
                    'document.audit.read',
                    'activity_log.read'
                )
            )
            """
        )
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE code IN
            (
                'document.audit.read',
                'activity_log.read'
            )
            """
        )
    )