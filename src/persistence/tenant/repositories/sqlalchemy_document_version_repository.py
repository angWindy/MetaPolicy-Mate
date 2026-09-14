from uuid import UUID

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_version import (
    DocumentVersion,
)
from src.domain.enums.document_processing_status import (
    DocumentProcessingStatus,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)


class SqlAlchemyDocumentVersionRepository(
    DocumentVersionRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        version_id: UUID,
    ) -> DocumentVersion | None:
        model = await self._session.get(
            DocumentVersionModel,
            version_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_id_for_update(
        self,
        version_id: UUID,
    ) -> DocumentVersion | None:
        statement = (
            select(
                DocumentVersionModel
            )
            .where(
                DocumentVersionModel.id
                == version_id
            )
            .with_for_update()
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_latest_by_document_id(
        self,
        document_id: UUID,
    ) -> DocumentVersion | None:
        result = await (
            self._session.execute(
                select(
                    DocumentVersionModel
                )
                .where(
                    DocumentVersionModel
                    .document_id
                    == document_id
                )
                .order_by(
                    DocumentVersionModel
                    .version_number
                    .desc()
                )
                .limit(1)
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def list_by_document_id(
        self,
        document_id: UUID,
    ) -> list[DocumentVersion]:
        result = await (
            self._session.execute(
                select(
                    DocumentVersionModel
                )
                .where(
                    DocumentVersionModel
                    .document_id
                    == document_id
                )
                .order_by(
                    DocumentVersionModel
                    .version_number
                )
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def add(
        self,
        version: DocumentVersion,
    ) -> None:
        self._session.add(
            DocumentVersionModel(
                id=version.id,
                document_id=(
                    version.document_id
                ),
                version_number=(
                    version.version_number
                ),
                processing_status=(
                    version
                    .processing_status
                    .value
                ),
                checksum=version.checksum,
                source_filename=(
                    version.source_filename
                ),
                object_key=(
                    version.object_key
                ),
                content_type=(
                    version.content_type
                ),
                size_bytes=(
                    version.size_bytes
                ),
                replaces_version_id=(
                    version
                    .replaces_version_id
                ),
                created_at=(
                    version.created_at
                ),
            )
        )

    async def update(
        self,
        version: DocumentVersion,
    ) -> None:
        model = await self._session.get(
            DocumentVersionModel,
            version.id,
        )

        if model is None:
            return

        model.processing_status = (
            version
            .processing_status
            .value
        )

    async def delete_by_document_id(
        self,
        document_id: UUID,
    ) -> int:
        statement = (
            sa_delete(
                DocumentVersionModel
            )
            .where(
                DocumentVersionModel
                .document_id
                == document_id
            )
        )
        result = await (
            self._session.execute(
                statement
            )
        )
        await self._session.flush()
        return result.rowcount or 0

    @staticmethod
    def _to_domain(
        model: DocumentVersionModel,
    ) -> DocumentVersion:
        return DocumentVersion(
            id=model.id,
            document_id=model.document_id,
            version_number=(
                model.version_number
            ),
            processing_status=(
                DocumentProcessingStatus(
                    model.processing_status
                )
            ),
            checksum=model.checksum,
            source_filename=(
                model.source_filename
            ),
            object_key=model.object_key,
            content_type=(
                model.content_type
            ),
            size_bytes=model.size_bytes,
            replaces_version_id=(
                model.replaces_version_id
            ),
            created_at=model.created_at,
        )