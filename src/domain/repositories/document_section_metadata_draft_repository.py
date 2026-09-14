from typing import Protocol
from uuid import UUID

from src.domain.entities.document_section_metadata_draft import (
    DocumentSectionMetadataDraft,
)


class DocumentSectionMetadataDraftRepository(
    Protocol
):
    async def get_by_id(
        self,
        draft_id: UUID,
    ) -> (
        DocumentSectionMetadataDraft
        | None
    ):
        ...

    async def get_by_chunk_id(
        self,
        chunk_id: UUID,
    ) -> (
        DocumentSectionMetadataDraft
        | None
    ):
        ...

    async def get_pending_by_version(
        self,
        version_id: UUID,
    ) -> list[
        DocumentSectionMetadataDraft
    ]:
        ...

    async def is_section_fully_approved(
        self,
        section_id: UUID,
    ) -> bool:
        ...

    async def save(
        self,
        draft: (
            DocumentSectionMetadataDraft
        ),
    ) -> None:
        ...