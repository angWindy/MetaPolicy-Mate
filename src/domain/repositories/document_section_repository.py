from typing import Protocol
from uuid import UUID

from src.domain.entities.document_section import (
    DocumentSection,
)


class DocumentSectionRepository(
    Protocol
):
    async def get_by_id(
        self,
        section_id: UUID,
    ) -> DocumentSection | None:
        ...

    async def get_by_id_for_update(
        self,
        section_id: UUID,
    ) -> DocumentSection | None:
        ...

    async def list_by_document(
        self,
        document_id: UUID,
    ) -> list[DocumentSection]:
        ...