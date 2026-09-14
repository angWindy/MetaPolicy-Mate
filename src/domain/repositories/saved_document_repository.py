from typing import Protocol
from uuid import UUID

from src.domain.entities.saved_document import (
    SavedDocument,
)


class SavedDocumentRepository(Protocol):
    """Repository for user-saved documents."""

    async def add(
        self,
        saved: SavedDocument,
    ) -> None:
        ...

    async def delete(
        self,
        user_id: UUID,
        document_id: UUID,
    ) -> bool:
        """Returns True if deleted, False if not found."""
        ...

    async def check_exists(
        self,
        user_id: UUID,
        document_id: UUID,
    ) -> bool:
        ...

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[SavedDocument], int]:
        """Returns (items, total_count)."""
        ...
