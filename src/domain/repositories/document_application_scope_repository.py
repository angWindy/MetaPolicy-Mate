from typing import Protocol
from uuid import UUID

from src.domain.entities.document_application_scope import (
    DocumentApplicationScope,
)


class DocumentApplicationScopeRepository(
    Protocol
):
    async def get_by_id(
        self,
        scope_id: UUID,
    ) -> DocumentApplicationScope | None:
        ...

    async def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[
        DocumentApplicationScope
    ]:
        ...

    async def exists(
        self,
        source_version_id: UUID,
        related_document_id: UUID,
        scope_type: str,
        scope_detail: str | None,
        reference_nature: str,
    ) -> bool:
        ...

    async def add(
        self,
        scope: DocumentApplicationScope,
    ) -> None:
        ...