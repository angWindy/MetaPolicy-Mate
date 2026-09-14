from uuid import UUID

from sqlalchemy import (
    delete,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_chunk import (
    DocumentChunk,
)
from src.domain.entities.document_ingestion_job import (
    DocumentIngestionJob,
)
from src.domain.entities.document_section import (
    DocumentSection,
)
from src.domain.repositories.document_digitization_repository import (
    DocumentDigitizationRepository,
)
from src.persistence.tenant.models.document_chunk import (
    DocumentChunkModel,
)
from src.persistence.tenant.models.document_ingestion_job import (
    DocumentIngestionJobModel,
)
from src.persistence.tenant.models.document_section import (
    DocumentSectionModel,
)
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)


class SqlAlchemyDocumentDigitizationRepository(
    DocumentDigitizationRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

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
        await self._session.execute(
            delete(
                DocumentChunkModel
            ).where(
                DocumentChunkModel.version_id
                == version_id
            )
        )

        await self._session.execute(
            delete(
                DocumentSectionModel
            ).where(
                DocumentSectionModel.version_id
                == version_id
            )
        )

        for section in sections:
            self._session.add(
                DocumentSectionModel(
                    id=section.id,
                    version_id=(
                        section.version_id
                    ),
                    section_type=(
                        section.section_type
                    ),
                    section_number=(
                        section.section_number
                    ),
                    heading=section.heading,
                    heading_path=(
                        section.heading_path
                    ),
                    content=section.content,
                    page=section.page,
                    sort_order=(
                        section.sort_order
                    ),
                )
            )

        # Flush so the section rows are visible before the chunk
        # inserts run — chunks carry an FK to document_sections and
        # SQLAlchemy otherwise tries to flush everything in one shot.
        await self._session.flush()

        for chunk in chunks:
            self._session.add(
                DocumentChunkModel(
                    id=chunk.id,
                    version_id=(
                        chunk.version_id
                    ),
                    section_id=(
                        chunk.section_id
                    ),
                    chunk_index=(
                        chunk.chunk_index
                    ),
                    text=chunk.text,
                    embedding_text=(
                        chunk.embedding_text
                    ),
                    content_hash=(
                        chunk.content_hash
                    ),
                    metadata_json=(
                        chunk.metadata
                    ),
                )
            )

    async def get_sections(
        self,
        version_id: UUID,
    ) -> list[DocumentSection]:
        result = await self._session.execute(
            select(
                DocumentSectionModel
            )
            .where(
                DocumentSectionModel.version_id
                == version_id
            )
            .order_by(
                DocumentSectionModel.sort_order
            )
        )

        return [
            DocumentSection(
                id=model.id,
                version_id=model.version_id,
                section_type=model.section_type,
                section_number=model.section_number,
                heading=model.heading,
                heading_path=list(
                    model.heading_path or []
                ),
                content=model.content,
                page=model.page,
                sort_order=model.sort_order,
            )
            for model
            in result.scalars().all()
        ]

    async def get_chunks(
        self,
        version_id: UUID,
    ) -> list[DocumentChunk]:
        result = await self._session.execute(
            select(
                DocumentChunkModel
            )
            .where(
                DocumentChunkModel.version_id
                == version_id
            )
            .order_by(
                DocumentChunkModel.chunk_index
            )
        )

        return [
            DocumentChunk(
                id=model.id,
                version_id=model.version_id,
                section_id=model.section_id,
                chunk_index=model.chunk_index,
                text=model.text,
                embedding_text=(
                    model.embedding_text
                ),
                content_hash=(
                    model.content_hash
                ),
                metadata=dict(
                    model.metadata_json or {}
                ),
            )
            for model
            in result.scalars().all()
        ]

    async def update_chunk_metadata(
        self,
        chunk_id: UUID,
        metadata: dict,
    ) -> None:
        model = await self._session.get(
            DocumentChunkModel,
            chunk_id,
        )

        if model is None:
            return

        current_metadata = dict(
            model.metadata_json
            or {}
        )

        current_metadata.update(
            dict(
                metadata
            )
        )

        model.metadata_json = (
            current_metadata
        )

    async def get_latest_job(
        self,
        version_id: UUID,
    ) -> DocumentIngestionJob | None:
        result = await self._session.execute(
            select(
                DocumentIngestionJobModel
            )
            .where(
                DocumentIngestionJobModel.version_id
                == version_id
            )
            .order_by(
                DocumentIngestionJobModel
                .started_at
                .desc()
            )
            .limit(1)
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._job_to_domain(
            model
        )

    async def add_job(
        self,
        job: DocumentIngestionJob,
    ) -> None:
        self._session.add(
            DocumentIngestionJobModel(
                id=job.id,
                version_id=job.version_id,
                status=job.status,
                warnings=job.warnings,
                error_message=(
                    job.error_message
                ),
                section_count=(
                    job.section_count
                ),
                chunk_count=(
                    job.chunk_count
                ),
                started_at=(
                    job.started_at
                ),
                completed_at=(
                    job.completed_at
                ),
            )
        )

    async def update_job(
        self,
        job: DocumentIngestionJob,
    ) -> None:
        model = await self._session.get(
            DocumentIngestionJobModel,
            job.id,
        )

        if model is None:
            return

        model.status = job.status
        model.warnings = job.warnings

        model.error_message = (
            job.error_message
        )

        model.section_count = (
            job.section_count
        )

        model.chunk_count = (
            job.chunk_count
        )

        model.completed_at = (
            job.completed_at
        )

    @staticmethod
    def _job_to_domain(
        model: DocumentIngestionJobModel,
    ) -> DocumentIngestionJob:
        return DocumentIngestionJob(
            id=model.id,
            version_id=model.version_id,
            status=model.status,
            warnings=list(
                model.warnings or []
            ),
            error_message=(
                model.error_message
            ),
            section_count=(
                model.section_count
            ),
            chunk_count=(
                model.chunk_count
            ),
            started_at=model.started_at,
            completed_at=(
                model.completed_at
            ),
        )

    async def update_document_access_metadata(
        self,
        document_id: UUID,
        access_scope: str,
        allowed_units: list[str],
    ) -> None:
        result = await (
            self._session.execute(
                select(
                    DocumentChunkModel
                )
                .join(
                    DocumentVersionModel,
                    DocumentVersionModel.id
                    == (
                        DocumentChunkModel
                        .version_id
                    ),
                )
                .where(
                    DocumentVersionModel
                    .document_id
                    == document_id
                )
            )
        )

        chunks = (
            result.scalars().all()
        )

        for chunk in chunks:
            metadata = dict(
                chunk.metadata_json
                or {}
            )

            metadata[
                "access_scope"
            ] = access_scope

            metadata[
                "allowed_units"
            ] = list(
                allowed_units
            )

            chunk.metadata_json = (
                metadata
            )