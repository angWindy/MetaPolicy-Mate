from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.domain.entities.document_changelog_entry import (
    DocumentChangelogEntry,
)


class DocumentChangelogRepository(
    Protocol
):
    async def get_by_document_id(
        self,
        document_id: UUID,
        action: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
        skip: int,
        limit: int,
    ) -> list[
        DocumentChangelogEntry
    ]:
        ...

    async def count_by_document_id(
        self,
        document_id: UUID,
        action: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> int:
        ...

    async def get_by_id(
        self,
        document_id: UUID,
        changelog_id: UUID,
    ) -> (
        DocumentChangelogEntry
        | None
    ):
        ...