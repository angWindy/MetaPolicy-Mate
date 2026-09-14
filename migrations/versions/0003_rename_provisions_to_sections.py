"""Replace the flat provisions schema with hierarchical sections."""

import sqlalchemy as sa
from alembic import op

revision = "0003_sections"
down_revision = "0002_add_rag_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("provisions", "sections")
    op.drop_index("ix_provisions_version_id", table_name="sections")
    op.create_index("ix_sections_version_id", "sections", ["version_id"])

    op.alter_column(
        "sections",
        "text",
        new_column_name="content",
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.drop_column("sections", "article")
    op.drop_column("sections", "clause")
    op.drop_column("sections", "point")
    op.drop_column("sections", "page")

    op.add_column("sections", sa.Column("parent_id", sa.String(36), nullable=True))
    op.add_column("sections", sa.Column("section_type", sa.String(30), nullable=True))
    op.add_column("sections", sa.Column("section_number", sa.String(50), nullable=True))
    op.add_column("sections", sa.Column("heading", sa.String(1000), nullable=True))
    op.create_foreign_key(
        "fk_sections_parent_id",
        "sections",
        "sections",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_sections_parent_id", "sections", ["parent_id"])

    op.drop_constraint("fk_chunks_provision_id", "chunks", type_="foreignkey")
    op.alter_column(
        "chunks",
        "provision_id",
        new_column_name="section_id",
        existing_type=sa.String(36),
        existing_nullable=True,
    )
    op.create_foreign_key(
        "fk_chunks_section_id",
        "chunks",
        "sections",
        ["section_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_chunks_section_id", "chunks", ["section_id"])


def downgrade() -> None:
    op.drop_constraint("fk_chunks_section_id", "chunks", type_="foreignkey")
    op.drop_index("ix_chunks_section_id", table_name="chunks")
    op.alter_column(
        "chunks",
        "section_id",
        new_column_name="provision_id",
        existing_type=sa.String(36),
        existing_nullable=True,
    )

    op.drop_constraint("fk_sections_parent_id", "sections", type_="foreignkey")
    op.drop_index("ix_sections_parent_id", table_name="sections")
    op.drop_column("sections", "heading")
    op.drop_column("sections", "section_number")
    op.drop_column("sections", "section_type")
    op.drop_column("sections", "parent_id")

    op.add_column("sections", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("sections", sa.Column("point", sa.String(50), nullable=True))
    op.add_column("sections", sa.Column("clause", sa.String(50), nullable=True))
    op.add_column("sections", sa.Column("article", sa.String(50), nullable=True))
    op.alter_column(
        "sections",
        "content",
        new_column_name="text",
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    op.drop_index("ix_sections_version_id", table_name="sections")
    op.rename_table("sections", "provisions")
    op.create_index("ix_provisions_version_id", "provisions", ["version_id"])
    op.create_foreign_key(
        "fk_chunks_provision_id",
        "chunks",
        "provisions",
        ["provision_id"],
        ["id"],
        ondelete="SET NULL",
    )
