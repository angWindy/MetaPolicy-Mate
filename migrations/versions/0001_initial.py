"""Initial governed RAG schema.

This revision is intentionally explicit. Importing the current ORM metadata
here would make the historical schema change whenever the application models
change and would cause later revisions to recreate already-existing tables.
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("document_number", sa.String(200), nullable=False),
        sa.Column("issued_by", sa.String(500), nullable=False),
        sa.Column("owner_department", sa.String(200), nullable=False),
        sa.Column("access_level", sa.String(30), nullable=False),
        sa.Column("allowed_departments", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("document_number", name="uq_documents_document_number"),
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("legal_status", sa.String(30), nullable=False),
        sa.Column("processing_status", sa.String(30), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("source_filename", sa.String(500), nullable=False),
        sa.Column("source_path", sa.String(2000), nullable=False),
        sa.Column(
            "replaces_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_version",
        ),
    )
    op.create_index(
        "ix_document_versions_document_id",
        "document_versions",
        ["document_id"],
    )
    op.create_index(
        "ix_document_versions_checksum",
        "document_versions",
        ["checksum"],
    )

    op.create_table(
        "provisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("heading_path", sa.JSON(), nullable=False),
        sa.Column("article", sa.String(50), nullable=True),
        sa.Column("clause", sa.String(50), nullable=True),
        sa.Column("point", sa.String(50), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_provisions_version_id", "provisions", ["version_id"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column(
            "version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provision_id", sa.String(36), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["provision_id"],
            ["provisions.id"],
            name="fk_chunks_provision_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_chunks_version_id", "chunks", ["version_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("department", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("resource_ids", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(200), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_user_feedback_request_id",
        "user_feedback",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_table("user_feedback")
    op.drop_table("audit_logs")
    op.drop_table("chunks")
    op.drop_table("provisions")
    op.drop_table("document_versions")
    op.drop_table("documents")
