from uuid import UUID

from sqlalchemy import (
    and_,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_application_scope import (
    DocumentApplicationScope,
)
from src.domain.enums.application_scope_type import (
    ApplicationScopeType,
)
from src.domain.enums.document_reference_nature import (
    DocumentReferenceNature,
)
from src.domain.repositories.document_application_scope_repository import (
    DocumentApplicationScopeRepository,
)
from src.persistence.tenant.models.document_application_scope import (
    DocumentApplicationScopeModel,
)


class SqlAlchemyDocumentApplicationScopeRepository(
    DocumentApplicationScopeRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        scope_id: UUID,
    ) -> DocumentApplicationScope | None:
        model = await self._session.get(
            DocumentApplicationScopeModel,
            scope_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[
        DocumentApplicationScope
    ]:
        result = await self._session.execute(
            select(
                DocumentApplicationScopeModel
            )
            .where(
                or_(
                    DocumentApplicationScopeModel
                    .source_document_id
                    == document_id,

                    DocumentApplicationScopeModel
                    .related_document_id
                    == document_id,
                )
            )
            .order_by(
                DocumentApplicationScopeModel
                .created_at
                .desc()
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def exists(
        self,
        source_version_id: UUID,
        related_document_id: UUID,
        scope_type: str,
        scope_detail: str | None,
        reference_nature: str,
    ) -> bool:
        conditions = [
            DocumentApplicationScopeModel
            .source_version_id
            == source_version_id,

            DocumentApplicationScopeModel
            .related_document_id
            == related_document_id,

            DocumentApplicationScopeModel
            .scope_type
            == scope_type,

            DocumentApplicationScopeModel
            .reference_nature
            == reference_nature,
        ]

        if scope_detail is None:
            conditions.append(
                DocumentApplicationScopeModel
                .scope_detail
                .is_(None)
            )
        else:
            conditions.append(
                DocumentApplicationScopeModel
                .scope_detail
                == scope_detail
            )

        result = await self._session.execute(
            select(
                DocumentApplicationScopeModel
                .id
            )
            .where(
                and_(
                    *conditions
                )
            )
            .limit(1)
        )

        return (
            result.scalar_one_or_none()
            is not None
        )

    async def add(
        self,
        scope: DocumentApplicationScope,
    ) -> None:
        self._session.add(
            DocumentApplicationScopeModel(
                id=scope.id,

                source_document_id=(
                    scope
                    .source_document_id
                ),

                source_version_id=(
                    scope
                    .source_version_id
                ),

                related_document_id=(
                    scope
                    .related_document_id
                ),

                scope_type=(
                    scope
                    .scope_type
                    .value
                ),

                scope_detail=(
                    scope.scope_detail
                ),

                reference_nature=(
                    scope
                    .reference_nature
                    .value
                ),

                created_by=(
                    scope.created_by
                ),

                created_at=(
                    scope.created_at
                ),
            )
        )

    @staticmethod
    def _to_domain(
        model: (
            DocumentApplicationScopeModel
        ),
    ) -> DocumentApplicationScope:
        return DocumentApplicationScope(
            id=model.id,

            source_document_id=(
                model.source_document_id
            ),

            source_version_id=(
                model.source_version_id
            ),

            related_document_id=(
                model.related_document_id
            ),

            scope_type=(
                ApplicationScopeType(
                    model.scope_type
                )
            ),

            scope_detail=(
                model.scope_detail
            ),

            reference_nature=(
                DocumentReferenceNature(
                    model.reference_nature
                )
            ),

            created_by=(
                model.created_by
            ),

            created_at=(
                model.created_at
            ),
        )