"""merge departments branches after fc6ccd3bf1b1 was made idempotent

Revision ID: 931b75fac2dd
Revises: 8a3f5c9e2b71, c91a7e4f2b60
Create Date: 2026-08-31 01:30:21.735963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '931b75fac2dd'
down_revision: Union[str, Sequence[str], None] = ('8a3f5c9e2b71', 'c91a7e4f2b60')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
