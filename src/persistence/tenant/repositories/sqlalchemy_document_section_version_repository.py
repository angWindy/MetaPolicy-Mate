from datetime import date
from uuid import UUID

from sqlalchemy import (
    func,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_section_version import (
    DocumentSectionVersion,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)
from src.persistence.tenant.models.document_section_version import (
    DocumentSectionVersionModel,
)


class SqlAlchemyDocumentSectionVersionRepository(
    DocumentSectionVersionRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        version_id: UUID,
    ) -> DocumentSectionVersion | None:
        model = await self._session.get(
            DocumentSectionVersionModel,
            version_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_by_section_id(
        self,
        section_id: UUID,
    ) -> list[
        DocumentSectionVersion
    ]:
        result = await self._session.execute(
            select(
                DocumentSectionVersionModel
            )
            .where(
                DocumentSectionVersionModel
                .section_id
                == section_id
            )
            .order_by(
                DocumentSectionVersionModel
                .version_number
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def get_current(
        self,
        section_id: UUID,
    ) -> DocumentSectionVersion | None:
        result = await self._session.execute(
            select(
                DocumentSectionVersionModel
            )
            .where(
                DocumentSectionVersionModel
                .section_id
                == section_id,
                DocumentSectionVersionModel
                .is_current
                .is_(True),
            )
            .limit(1)
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_next_version_number(
        self,
        section_id: UUID,
    ) -> int:
        result = await self._session.execute(
            select(
                func.max(
                    DocumentSectionVersionModel
                    .version_number
                )
            )
            .where(
                DocumentSectionVersionModel
                .section_id
                == section_id
            )
        )

        current_max = (
            result.scalar_one_or_none()
        )

        return (
            int(current_max or 0)
            + 1
        )

    async def has_overlapping_effective_period(
        self,
        section_id: UUID,
        effective_from: date,
        effective_to: date | None,
        exclude_version_id: (
            UUID | None
        ) = None,
    ) -> bool:
        query = select(
            DocumentSectionVersionModel.id
        ).where(
            DocumentSectionVersionModel
            .section_id
            == section_id
        )

        if effective_to is None:
            query = query.where(
                or_(
                    DocumentSectionVersionModel
                    .effective_to
                    .is_(None),
                    DocumentSectionVersionModel
                    .effective_to
                    >= effective_from,
                )
            )
        else:
            query = query.where(
                DocumentSectionVersionModel
                .effective_from
                <= effective_to,
                or_(
                    DocumentSectionVersionModel
                    .effective_to
                    .is_(None),
                    DocumentSectionVersionModel
                    .effective_to
                    >= effective_from,
                ),
            )

        if (
            exclude_version_id
            is not None
        ):
            query = query.where(
                DocumentSectionVersionModel
                .id
                != exclude_version_id
            )

        query = query.limit(1)

        result = await self._session.execute(
            query
        )

        return (
            result.scalar_one_or_none()
            is not None
        )

    async def add(
        self,
        version: DocumentSectionVersion,
    ) -> None:
        self._session.add(
            DocumentSectionVersionModel(
                id=version.id,
                section_id=(
                    version.section_id
                ),
                version_number=(
                    version.version_number
                ),
                content=version.content,
                effective_from=(
                    version.effective_from
                ),
                effective_to=(
                    version.effective_to
                ),
                is_current=(
                    version.is_current
                ),
                created_at=(
                    version.created_at
                ),
                updated_at=(
                    version.updated_at
                ),
            )
        )

    async def update(
        self,
        version: DocumentSectionVersion,
    ) -> None:
        model = await self._session.get(
            DocumentSectionVersionModel,
            version.id,
        )

        if model is None:
            return

        model.effective_from = (
            version.effective_from
        )

        model.effective_to = (
            version.effective_to
        )

        model.is_current = (
            version.is_current
        )

        model.updated_at = (
            version.updated_at
        )

    @staticmethod
    def _to_domain(
        model: (
            DocumentSectionVersionModel
        ),
    ) -> DocumentSectionVersion:
        return DocumentSectionVersion(
            id=model.id,
            section_id=model.section_id,
            version_number=(
                model.version_number
            ),
            content=model.content,
            effective_from=(
                model.effective_from
            ),
            effective_to=(
                model.effective_to
            ),
            is_current=model.is_current,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )