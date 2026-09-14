from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_section import (
    DocumentSection,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.persistence.tenant.models.document_section import (
    DocumentSectionModel,
)
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)


class SqlAlchemyDocumentSectionRepository(
    DocumentSectionRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        section_id: UUID,
    ) -> DocumentSection | None:
        model = await self._session.get(
            DocumentSectionModel,
            section_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_id_for_update(
        self,
        section_id: UUID,
    ) -> DocumentSection | None:
        statement = (
            select(
                DocumentSectionModel
            )
            .where(
                DocumentSectionModel.id
                == section_id
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

    async def list_by_document(
        self,
        document_id: UUID,
    ) -> list[DocumentSection]:
        """Return all sections (Điều, Khoản, Chương...) for a document,
        sorted by ``sort_order``. Resolves ``version_id`` through the
        latest version of the document."""
        statement = (
            select(
                DocumentSectionModel
            )
            .join(
                DocumentVersionModel,
                DocumentVersionModel.id
                == DocumentSectionModel.version_id,
            )
            .where(
                DocumentVersionModel.document_id
                == document_id
            )
            .order_by(
                DocumentSectionModel.sort_order
            )
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    @staticmethod
    def _to_domain(
        model: DocumentSectionModel,
    ) -> DocumentSection:
        return DocumentSection(
            id=model.id,
            version_id=model.version_id,
            section_type=model.section_type,
            section_number=model.section_number,
            heading=model.heading,
            heading_path=model.heading_path,
            content=model.content,
            page=model.page,
            sort_order=model.sort_order,
        )