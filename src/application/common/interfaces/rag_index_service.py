from typing import Protocol
from uuid import UUID

from src.domain.entities.document import (
    Document,
)
from src.domain.entities.document_chunk import (
    DocumentChunk,
)
from src.domain.entities.document_version import (
    DocumentVersion,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)


class RagIndexService(
    Protocol
):
    async def index_chunks(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        chunks: list[DocumentChunk],
        allowed_units: list[str],
    ) -> None:
        ...

    async def update_document_access(
        self,
        *,
        document_id: UUID,
        access_scope: DocumentAccessScope,
        allowed_units: list[str],
    ) -> None:
        ...

    async def reindex_section(
        self,
        *,
        section_id: UUID,
    ) -> None:
        ...