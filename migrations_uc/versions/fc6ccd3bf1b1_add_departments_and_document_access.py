"""add departments and document access

Revision ID: fc6ccd3bf1b1
Revises: e12aee307c05
Create Date: 2026-08-23 14:32:55.395648

NOTE: This migration was originally a parallel branch to
``8a3f5c9e2b71_add_departments_and_document_departments`` which now lives
on the canonical branch and has already been applied. The DDL here is
functionally identical (departments table + department_id FK on users +
document_departments join + access_scope column on documents). To keep
the other alembic branch (``fc6cc -> 6c2a41874682 -> ... -> c91a7e4f2b60``)
reachable, this upgrade is now an idempotent no-op: every object it would
create already exists in the DB. The matching ``downgrade()`` is also a
no-op for the same reason.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import (
    postgresql,
)

# revision identifiers, used by Alembic.
revision: str = 'fc6ccd3bf1b1'
down_revision: Union[str, Sequence[str], None] = 'e12aee307c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Idempotent no-op: 8a3f5c9e2b71 already created departments +
    document_departments + users.department_id + documents.access_scope.
    """
    # The full DDL was originally here but was made a no-op after
    # 8a3f5c9e2b71 was promoted to the canonical branch. See the module
    # docstring above for context.
    return


def downgrade() -> None:
    """Idempotent no-op: see upgrade()."""
    return