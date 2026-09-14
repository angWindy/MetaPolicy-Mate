"""add document digitization

Revision ID: 6c2a41874682
Revises: fc6ccd3bf1b1
Create Date: 2026-08-24 10:04:22.859338

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import (
    postgresql,
)


# revision identifiers, used by Alembic.
revision: str = '6c2a41874682'
down_revision: Union[str, Sequence[str], None] = 'fc6ccd3bf1b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
    "document_sections",

    sa.Column(
        "id",
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
        "section_type",
        sa.String(30),
        nullable=True,
    ),

    sa.Column(
        "section_number",
        sa.String(50),
        nullable=True,
    ),

    sa.Column(
        "heading",
        sa.String(1000),
        nullable=True,
    ),

    sa.Column(
        "heading_path",
        sa.JSON(),
        nullable=False,
    ),

    sa.Column(
        "content",
        sa.Text(),
        nullable=False,
    ),

    sa.Column(
        "page",
        sa.Integer(),
        nullable=True,
    ),

    sa.Column(
        "sort_order",
        sa.Integer(),
        nullable=False,
    ),

    sa.ForeignKeyConstraint(
        ["version_id"],
        ["document_versions.id"],
        ondelete="CASCADE",
    ),

    sa.PrimaryKeyConstraint(
        "id"
    ),
)
    op.create_index(
        "ix_document_sections_version_id",
        "document_sections",
        ["version_id"],
    )


    op.create_table(
        "document_chunks",

        sa.Column(
            "id",
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
            "chunk_index",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "text",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "embedding_text",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
        ),

        sa.Column(
            "metadata_json",
            sa.JSON(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["section_id"],
            ["document_sections.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "version_id",
            "chunk_index",
            name=(
                "uq_document_chunks_"
                "version_chunk_index"
            ),
        ),
    )

    op.create_index(
        "ix_document_chunks_version_id",
        "document_chunks",
        ["version_id"],
    )

    op.create_index(
        "ix_document_chunks_section_id",
        "document_chunks",
        ["section_id"],
    )


    op.create_table(
        "document_ingestion_jobs",

        sa.Column(
            "id",
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
            "status",
            sa.String(30),
            nullable=False,
        ),

        sa.Column(
            "warnings",
            sa.JSON(),
            nullable=False,
        ),

        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "section_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "started_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),
    )

    op.create_index(
        "ix_document_ingestion_jobs_version_id",
        "document_ingestion_jobs",
        ["version_id"],
    )

    op.create_index(
        "ix_document_ingestion_jobs_status",
        "document_ingestion_jobs",
        ["status"],
    )

    op.execute(
        """
        INSERT INTO permissions
            (
                id,
                code,
                name,
                module,
                description
            )
        VALUES
            (
                gen_random_uuid(),
                'document.process',
                'Process documents',
                'document',
                'Digitize and chunk document sources'
            )
        ON CONFLICT (code)
        DO NOTHING
        """
    )

    op.execute(
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
          AND p.code = 'document.process'
          AND NOT EXISTS
          (
              SELECT 1
              FROM role_permissions rp
              WHERE rp.role_id = r.id
                AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE permission_id IN
        (
            SELECT id
            FROM permissions
            WHERE code = 'document.process'
        )
        """
    )

    op.execute(
        """
        DELETE FROM permissions
        WHERE code = 'document.process'
        """
    )

    op.drop_index(
        "ix_document_ingestion_jobs_status",
        table_name="document_ingestion_jobs",
    )

    op.drop_index(
        "ix_document_ingestion_jobs_version_id",
        table_name="document_ingestion_jobs",
    )

    op.drop_table(
        "document_ingestion_jobs"
    )

    op.drop_index(
        "ix_document_chunks_section_id",
        table_name="document_chunks",
    )

    op.drop_index(
        "ix_document_chunks_version_id",
        table_name="document_chunks",
    )

    op.drop_table(
        "document_chunks"
    )

    op.drop_index(
        "ix_document_sections_version_id",
        table_name="document_sections",
    )

    op.drop_table(
        "document_sections"
    )