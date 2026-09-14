"""add document metadata drafts

Revision ID: 13a2f34a5d37
Revises: 6c2a41874682
Create Date: 2026-08-24 10:53:05.548685

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import (
    postgresql,
)

# revision identifiers, used by Alembic.
revision: str = '13a2f34a5d37'
down_revision: Union[str, Sequence[str], None] = '6c2a41874682'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_metadata_drafts",

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
            "document_number",
            sa.String(100),
            nullable=True,
        ),

        sa.Column(
            "document_number_confidence",
            sa.Float(),
            nullable=False,
        ),

        sa.Column(
            "title",
            sa.String(1000),
            nullable=True,
        ),

        sa.Column(
            "title_confidence",
            sa.Float(),
            nullable=False,
        ),

        sa.Column(
            "needs_human_review",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "rationale",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "raw_header_text",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            server_default=sa.func.now(),
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

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "version_id",
            name=(
                "uq_document_metadata_"
                "drafts_version"
            ),
        ),
    )

    op.create_index(
        "ix_document_metadata_drafts_document_id",
        "document_metadata_drafts",
        ["document_id"],
    )

    op.create_index(
        "ix_document_metadata_drafts_status",
        "document_metadata_drafts",
        ["status"],
    )

    op.create_table(
        "document_cross_reference_drafts",

        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "metadata_draft_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "source_document_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "source_version_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),

        sa.Column(
            "referenced_document_number",
            sa.String(100),
            nullable=False,
        ),

        sa.Column(
            "referenced_document_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=True,
        ),

        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),

        sa.Column(
            "context_text",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["metadata_draft_id"],
            ["document_metadata_drafts.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["source_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["referenced_document_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "source_version_id",
            "referenced_document_number",
            name=(
                "uq_document_cross_reference_"
                "draft_version_number"
            ),
        ),
    )

    op.create_index(
        "ix_document_cross_reference_drafts_metadata_draft_id",
        "document_cross_reference_drafts",
        ["metadata_draft_id"],
    )

    op.create_index(
        "ix_document_cross_reference_drafts_source_document_id",
        "document_cross_reference_drafts",
        ["source_document_id"],
    )

    op.create_index(
        "ix_document_cross_reference_drafts_source_version_id",
        "document_cross_reference_drafts",
        ["source_version_id"],
    )

    op.create_index(
        "ix_document_cross_reference_drafts_referenced_document_id",
        "document_cross_reference_drafts",
        ["referenced_document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_cross_reference_drafts_referenced_document_id",
        table_name=(
            "document_cross_reference_drafts"
        ),
    )

    op.drop_index(
        "ix_document_cross_reference_drafts_source_version_id",
        table_name=(
            "document_cross_reference_drafts"
        ),
    )

    op.drop_index(
        "ix_document_cross_reference_drafts_source_document_id",
        table_name=(
            "document_cross_reference_drafts"
        ),
    )

    op.drop_index(
        "ix_document_cross_reference_drafts_metadata_draft_id",
        table_name=(
            "document_cross_reference_drafts"
        ),
    )

    op.drop_table(
        "document_cross_reference_drafts"
    )

    op.drop_index(
        "ix_document_metadata_drafts_status",
        table_name=(
            "document_metadata_drafts"
        ),
    )

    op.drop_index(
        "ix_document_metadata_drafts_document_id",
        table_name=(
            "document_metadata_drafts"
        ),
    )

    op.drop_table(
        "document_metadata_drafts"
    )