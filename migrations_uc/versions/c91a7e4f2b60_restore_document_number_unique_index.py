"""restore document number unique index

Revision ID: c91a7e4f2b60
Revises: 12176dce1d93
"""

from typing import (
    Sequence,
    Union,
)

from alembic import op


revision: str = "c91a7e4f2b60"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "12176dce1d93"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    # Dùng IF NOT EXISTS để tương thích
    # database đã được tạo index thủ công.
    #
    # Nếu đang có document_number trùng,
    # PostgreSQL sẽ dừng migration thay vì
    # âm thầm giữ dữ liệu không hợp lệ.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            uq_documents_document_number_ci
        ON documents
        (
            lower(document_number::text)
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS
            uq_documents_document_number_ci
        """
    )