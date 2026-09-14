"""Add RAG tables: ingestion_jobs, approval_records, access_policies, document_relations."""

import sqlalchemy as sa
from alembic import op

revision = "0002_add_rag_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ingestion_jobs
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="received"),
        sa.Column("parser_name", sa.String(50), nullable=True),
        sa.Column("parser_warnings", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("chunking_warnings", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("section_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_ingestion_jobs_version_id", "ingestion_jobs", ["version_id"], unique=False)
    op.create_index("ix_ingestion_jobs_status", "ingestion_jobs", ["status"], unique=False)

    # approval_records
    op.create_table(
        "approval_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("reviewer_id", sa.String(200), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("warnings_snapshot", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("decided_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_approval_records_version_id", "approval_records", ["version_id"], unique=False)
    op.create_index("ix_approval_records_decision", "approval_records", ["decision"], unique=False)

    # access_policies
    op.create_table(
        "access_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("access_level", sa.String(30), nullable=False),
        sa.Column("allowed_roles", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("allowed_units", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("applies_to", sa.String(20), nullable=False, server_default="document"),
        sa.Column("applies_to_ids", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("valid_from", sa.DateTime, nullable=True),
        sa.Column("valid_to", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_access_policies_access_level", "access_policies", ["access_level"], unique=False)

    # document_relations
    op.create_table(
        "document_relations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False, server_default="unidirectional"),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_document_relations_source", "document_relations", ["source_document_id"], unique=False)
    op.create_index("ix_document_relations_target", "document_relations", ["target_document_id"], unique=False)
    op.create_unique_constraint(
        "uq_document_relation", "document_relations",
        ["source_document_id", "target_document_id", "relation_type"],
    )


def downgrade() -> None:
    op.drop_table("document_relations")
    op.drop_table("access_policies")
    op.drop_table("approval_records")
    op.drop_table("ingestion_jobs")
