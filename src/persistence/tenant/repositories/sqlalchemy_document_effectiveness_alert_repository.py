from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.document_effectiveness_alert import (
    DocumentEffectivenessAlert,
)
from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)
from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)
from src.persistence.tenant.models.document_effectiveness_alert import (
    DocumentEffectivenessAlertModel,
)


class SqlAlchemyDocumentEffectivenessAlertRepository(
    DocumentEffectivenessAlertRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        alert_id: UUID,
    ) -> DocumentEffectivenessAlert | None:
        model = await self._session.get(
            DocumentEffectivenessAlertModel,
            alert_id,
        )

        if model is None:
            return None

        return self._to_domain(
            model
        )

    async def get_list(
        self,
        status: (
            DocumentEffectivenessAlertStatus
            | None
        ),
        skip: int,
        limit: int,
    ) -> list[
        DocumentEffectivenessAlert
    ]:
        statement = select(
            DocumentEffectivenessAlertModel
        )

        if status is not None:
            statement = statement.where(
                DocumentEffectivenessAlertModel.status
                == status.value
            )

        statement = (
            statement
            .order_by(
                DocumentEffectivenessAlertModel
                .effective_date
                .asc()
                .nulls_last(),
                DocumentEffectivenessAlertModel
                .created_at
                .desc(),
            )
            .offset(skip)
            .limit(limit)
        )

        result = await self._session.execute(
            statement
        )

        return [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

    async def count(
        self,
        status: (
            DocumentEffectivenessAlertStatus
            | None
        ),
    ) -> int:
        statement = select(
            func.count(
                DocumentEffectivenessAlertModel.id
            )
        )

        if status is not None:
            statement = statement.where(
                DocumentEffectivenessAlertModel.status
                == status.value
            )

        result = await self._session.execute(
            statement
        )

        return int(
            result.scalar_one()
        )

    async def add(
        self,
        alert: DocumentEffectivenessAlert,
    ) -> None:
        self._session.add(
            DocumentEffectivenessAlertModel(
                id=alert.id,
                new_document_number=(
                    alert.new_document_number
                ),
                new_document_title=(
                    alert.new_document_title
                ),
                announced_date=(
                    alert.announced_date
                ),
                effective_date=(
                    alert.effective_date
                ),
                affected_document_id=(
                    alert.affected_document_id
                ),
                status=(
                    alert.status.value
                ),
                note=alert.note,
                created_by=(
                    alert.created_by
                ),
                created_at=(
                    alert.created_at
                ),
                updated_at=(
                    alert.updated_at
                ),
            )
        )

    async def update(
        self,
        alert: DocumentEffectivenessAlert,
    ) -> None:
        model = await self._session.get(
            DocumentEffectivenessAlertModel,
            alert.id,
        )

        if model is None:
            return

        model.status = (
            alert.status.value
        )

        model.note = alert.note

        model.updated_at = (
            alert.updated_at
        )

    @staticmethod
    def _to_domain(
        model: DocumentEffectivenessAlertModel,
    ) -> DocumentEffectivenessAlert:
        return DocumentEffectivenessAlert(
            id=model.id,
            new_document_number=(
                model.new_document_number
            ),
            new_document_title=(
                model.new_document_title
            ),
            announced_date=(
                model.announced_date
            ),
            effective_date=(
                model.effective_date
            ),
            affected_document_id=(
                model.affected_document_id
            ),
            status=(
                DocumentEffectivenessAlertStatus(
                    model.status
                )
            ),
            note=model.note,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )