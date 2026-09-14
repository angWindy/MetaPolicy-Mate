"""add document section metadata drafts

Revision ID: 491b8833a627
Revises: f625ef4b8902
Create Date: 2026-08-24 17:48:48.666712

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '491b8833a627'
down_revision: Union[str, Sequence[str], None] = 'f625ef4b8902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_section_metadata_drafts",

        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "document_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "version_id",
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
            nullable=True,
        ),

        sa.Column(
            "chunk_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            server_default=(
                sa.text("'{}'::jsonb")
            ),
            nullable=False,
        ),

        sa.Column(
            "cross_references_json",
            postgresql.JSONB(),
            server_default=(
                sa.text("'[]'::jsonb")
            ),
            nullable=False,
        ),

        sa.Column(
            "needs_human_review",
            sa.Boolean(),
            server_default=(
                sa.text("true")
            ),
            nullable=False,
        ),

        sa.Column(
            "rationale",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "status",
            sa.String(
                length=30
            ),
            nullable=False,
        ),

        sa.Column(
            "reviewed_by",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),

        sa.Column(
            "reviewed_at",
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
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["document_chunks.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "chunk_id",
            name=(
                "uq_section_metadata_"
                "draft_chunk"
            ),
        ),
    )

    op.create_index(
        "ix_section_metadata_drafts_"
        "document_id",
        "document_section_metadata_drafts",
        ["document_id"],
    )

    op.create_index(
        "ix_section_metadata_drafts_"
        "version_id",
        "document_section_metadata_drafts",
        ["version_id"],
    )

    op.create_index(
        "ix_section_metadata_drafts_"
        "section_id",
        "document_section_metadata_drafts",
        ["section_id"],
    )

    op.create_index(
        "ix_section_metadata_drafts_"
        "chunk_id",
        "document_section_metadata_drafts",
        ["chunk_id"],
    )

    op.create_index(
        "ix_section_metadata_drafts_"
        "status",
        "document_section_metadata_drafts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_section_metadata_drafts_status",
        table_name=(
            "document_section_metadata_drafts"
        ),
    )

    op.drop_index(
        "ix_section_metadata_drafts_chunk_id",
        table_name=(
            "document_section_metadata_drafts"
        ),
    )

    op.drop_index(
        "ix_section_metadata_drafts_section_id",
        table_name=(
            "document_section_metadata_drafts"
        ),
    )

    op.drop_index(
        "ix_section_metadata_drafts_version_id",
        table_name=(
            "document_section_metadata_drafts"
        ),
    )

    op.drop_index(
        "ix_section_metadata_drafts_document_id",
        table_name=(
            "document_section_metadata_drafts"
        ),
    )

    op.drop_table(
        "document_section_metadata_drafts"
    )