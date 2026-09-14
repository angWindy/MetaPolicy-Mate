from typing import Protocol
from uuid import UUID

from src.domain.entities.document_chunk import (
    DocumentChunk,
)
from src.domain.entities.document_ingestion_job import (
    DocumentIngestionJob,
)
from src.domain.entities.document_section import (
    DocumentSection,
)


class DocumentDigitizationRepository(
    Protocol
):
    async def replace_content(
        self,
        version_id: UUID,
        sections: list[
            DocumentSection
        ],
        chunks: list[
            DocumentChunk
        ],
    ) -> None:
        ...

    async def get_sections(
        self,
        version_id: UUID,
    ) -> list[DocumentSection]:
        ...

    async def get_chunks(
        self,
        version_id: UUID,
    ) -> list[DocumentChunk]:
        ...

    async def update_chunk_metadata(
        self,
        chunk_id: UUID,
        metadata: dict,
    ) -> None:
        ...

    async def get_latest_job(
        self,
        version_id: UUID,
    ) -> (
        DocumentIngestionJob
        | None
    ):
        ...

    async def add_job(
        self,
        job: DocumentIngestionJob,
    ) -> None:
        ...

    async def update_job(
        self,
        job: DocumentIngestionJob,
    ) -> None:
        ...

    async def update_document_access_metadata(
        self,
        document_id: UUID,
        access_scope: str,
        allowed_units: list[str],
    ) -> None:
        ...