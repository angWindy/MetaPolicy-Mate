from datetime import date
from typing import Protocol
from uuid import UUID

from src.domain.entities.document_section_version import (
    DocumentSectionVersion,
)


class DocumentSectionVersionRepository(
    Protocol
):
    async def get_by_id(
        self,
        version_id: UUID,
    ) -> DocumentSectionVersion | None:
        ...

    async def get_by_section_id(
        self,
        section_id: UUID,
    ) -> list[
        DocumentSectionVersion
    ]:
        ...

    async def get_current(
        self,
        section_id: UUID,
    ) -> DocumentSectionVersion | None:
        ...

    async def get_next_version_number(
        self,
        section_id: UUID,
    ) -> int:
        ...

    async def has_overlapping_effective_period(
        self,
        section_id: UUID,
        effective_from: date,
        effective_to: date | None,
        exclude_version_id: (
            UUID | None
        ) = None,
    ) -> bool:
        ...

    async def add(
        self,
        version: DocumentSectionVersion,
    ) -> None:
        ...

    async def update(
        self,
        version: DocumentSectionVersion,
    ) -> None:
        ...