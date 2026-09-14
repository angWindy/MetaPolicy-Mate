"""add unique document number index

Revision ID: cc0902b4e6c6
Revises: 0004_expand_chunk_content_hash
Create Date: 2026-08-19 11:25:15.283533
"""
from alembic import op
import sqlalchemy as sa


revision = 'cc0902b4e6c6'
down_revision = '0004_expand_chunk_content_hash'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

