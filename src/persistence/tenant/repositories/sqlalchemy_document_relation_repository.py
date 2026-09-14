from uuid import UUID

from sqlalchemy import (
    or_,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_relation import (
    DocumentRelation,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.domain.enums.document_relation_type import (
    DocumentRelationType,
)
from src.domain.repositories.document_relation_repository import (
    DocumentRelationRepository,
)
from src.persistence.tenant.models.document import (
    DocumentModel,
)
from src.persistence.tenant.models.document_relation import (
    DocumentRelationModel,
)


class SqlAlchemyDocumentRelationRepository(
    DocumentRelationRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        relation_id: UUID,
    ) -> DocumentRelation | None:
        model = await self._session.get(
            DocumentRelationModel,
            relation_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[DocumentRelation]:
        result = await self._session.execute(
            select(
                DocumentRelationModel
            )
            .where(
                or_(
                    DocumentRelationModel
                    .source_document_id
                    == document_id,

                    DocumentRelationModel
                    .target_document_id
                    == document_id,
                )
            )
            .order_by(
                DocumentRelationModel
                .created_at
                .desc()
            )
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def get_effective_superseding_relation(
        self,
        target_document_id: UUID,
    ) -> DocumentRelation | None:
        result = await self._session.execute(
            select(
                DocumentRelationModel
            )
            .join(
                DocumentModel,
                DocumentModel.id
                == DocumentRelationModel
                .source_document_id,
            )
            .where(
                DocumentRelationModel
                .target_document_id
                == target_document_id
            )
            .where(
                DocumentRelationModel
                .relation_type
                == DocumentRelationType
                .SUPERSEDES
                .value
            )
            .where(
                DocumentModel.legal_status
                == DocumentLegalStatus
                .DANG_HIEU_LUC
                .value
            )
            .order_by(
                DocumentRelationModel
                .created_at
                .desc()
            )
            .limit(1)
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def add(
        self,
        relation: DocumentRelation,
    ) -> None:
        self._session.add(
            DocumentRelationModel(
                id=relation.id,
                source_document_id=(
                    relation.source_document_id
                ),
                target_document_id=(
                    relation.target_document_id
                ),
                relation_type=(
                    relation.relation_type.value
                ),
                note=relation.note,
                created_at=(
                    relation.created_at
                ),
            )
        )

    async def delete(
        self,
        relation: DocumentRelation,
    ) -> None:
        model = await self._session.get(
            DocumentRelationModel,
            relation.id,
        )

        if model is not None:
            await self._session.delete(
                model
            )

    @staticmethod
    def _to_domain(
        model: DocumentRelationModel,
    ) -> DocumentRelation:
        return DocumentRelation(
            id=model.id,
            source_document_id=(
                model.source_document_id
            ),
            target_document_id=(
                model.target_document_id
            ),
            relation_type=(
                DocumentRelationType(
                    model.relation_type
                )
            ),
            note=model.note,
            created_at=model.created_at,
        )