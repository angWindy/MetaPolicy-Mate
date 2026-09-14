from typing import Protocol
from uuid import UUID

from src.domain.entities.document_version import (
    DocumentVersion,
)


class DocumentVersionRepository(
    Protocol
):
    async def get_by_id(
        self,
        version_id: UUID,
    ) -> DocumentVersion | None:
        ...

    async def get_by_id_for_update(
        self,
        version_id: UUID,
    ) -> DocumentVersion | None:
        ...

    async def get_latest_by_document_id(
        self,
        document_id: UUID,
    ) -> DocumentVersion | None:
        ...

    async def list_by_document_id(
        self,
        document_id: UUID,
    ) -> list[DocumentVersion]:
        ...

    async def add(
        self,
        version: DocumentVersion,
    ) -> None:
        ...

    async def update(
        self,
        version: DocumentVersion,
    ) -> None:
        ...

    async def delete_by_document_id(
        self,
        document_id: UUID,
    ) -> int:
        ...