"""add document audit read permission

Revision ID: f625ef4b8902
Revises: b53437b71ffb
Create Date: 2026-08-24 16:31:17.371831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f625ef4b8902'
down_revision: Union[str, Sequence[str], None] = 'b53437b71ffb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from uuid import uuid4

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
            'document.audit.read',
            'Read document audit history',
            'document',
            'View document changelog and audit history'
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
        AND p.code = 'document.audit.read'
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO role_permissions (
            role_id,
            permission_id
        )
        SELECT DISTINCT
            rp.role_id,
            audit_permission.id
        FROM role_permissions rp
        JOIN permissions approve_permission
            ON approve_permission.id = rp.permission_id
        CROSS JOIN permissions audit_permission
        WHERE approve_permission.code = 'document.approve'
            AND audit_permission.code = 'document.audit.read'
        ON CONFLICT DO NOTHING
        """
    )

def downgrade() -> None:
    """Downgrade schema."""
    pass
