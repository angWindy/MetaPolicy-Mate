from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.static_threshold import (
    StaticThreshold,
)
from src.domain.enums.static_threshold_status import (
    StaticThresholdStatus,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)
from src.persistence.tenant.models.static_threshold import (
    StaticThresholdModel,
)


class SqlAlchemyStaticThresholdRepository(
    StaticThresholdRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_by_id(
        self,
        threshold_id: UUID,
    ) -> StaticThreshold | None:
        model = await self._session.get(
            StaticThresholdModel,
            threshold_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_history(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> list[StaticThreshold]:
        result = await (
            self._session.execute(
                select(
                    StaticThresholdModel
                )
                .where(
                    StaticThresholdModel
                    .threshold_key
                    == threshold_key,
                    StaticThresholdModel
                    .scope_key
                    == scope_key,
                )
                .order_by(
                    StaticThresholdModel
                    .version_number
                )
            )
        )

        return [
            self._to_domain(item)
            for item
            in result.scalars().all()
        ]

    async def get_current(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> StaticThreshold | None:
        result = await (
            self._session.execute(
                select(
                    StaticThresholdModel
                )
                .where(
                    StaticThresholdModel
                    .threshold_key
                    == threshold_key,
                    StaticThresholdModel
                    .scope_key
                    == scope_key,
                    StaticThresholdModel
                    .is_current
                    .is_(True),
                )
                .limit(1)
            )
        )

        model = (
            result.scalar_one_or_none()
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_verified_current(
        self,
    ) -> list[StaticThreshold]:
        result = await (
            self._session.execute(
                select(
                    StaticThresholdModel
                )
                .where(
                    StaticThresholdModel
                    .status
                    == (
                        StaticThresholdStatus
                        .VERIFIED.value
                    ),
                    StaticThresholdModel
                    .is_current
                    .is_(True),
                )
                .order_by(
                    StaticThresholdModel
                    .threshold_key,
                    StaticThresholdModel
                    .scope_key,
                )
            )
        )

        return [
            self._to_domain(item)
            for item
            in result.scalars().all()
        ]

    async def get_next_version_number(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> int:
        result = await (
            self._session.execute(
                select(
                    func.max(
                        StaticThresholdModel
                        .version_number
                    )
                )
                .where(
                    StaticThresholdModel
                    .threshold_key
                    == threshold_key,
                    StaticThresholdModel
                    .scope_key
                    == scope_key,
                )
            )
        )

        current_max = (
            result.scalar_one_or_none()
        )

        return (
            int(current_max or 0)
            + 1
        )

    async def add(
        self,
        threshold: StaticThreshold,
    ) -> None:
        self._session.add(
            StaticThresholdModel(
                id=threshold.id,
                threshold_key=(
                    threshold.threshold_key
                ),
                scope_key=(
                    threshold.scope_key
                ),
                version_number=(
                    threshold.version_number
                ),
                name=threshold.name,
                operator=threshold.operator,
                value=threshold.value,
                unit=threshold.unit,
                condition_text=(
                    threshold.condition_text
                ),
                section_id=(
                    threshold.section_id
                ),
                section_version_id=(
                    threshold.section_version_id
                ),
                status=(
                    threshold.status.value
                ),
                is_current=(
                    threshold.is_current
                ),
                verified_at=(
                    threshold.verified_at
                ),
                created_at=(
                    threshold.created_at
                ),
                updated_at=(
                    threshold.updated_at
                ),
            )
        )

    async def update(
        self,
        threshold: StaticThreshold,
    ) -> None:
        model = await self._session.get(
            StaticThresholdModel,
            threshold.id,
        )

        if model is None:
            return

        model.status = (
            threshold.status.value
        )

        model.is_current = (
            threshold.is_current
        )

        model.verified_at = (
            threshold.verified_at
        )

        model.updated_at = (
            threshold.updated_at
        )

    @staticmethod
    def _to_domain(
        model: StaticThresholdModel,
    ) -> StaticThreshold:
        return StaticThreshold(
            id=model.id,
            threshold_key=(
                model.threshold_key
            ),
            scope_key=(
                model.scope_key
            ),
            version_number=(
                model.version_number
            ),
            name=model.name,
            operator=model.operator,
            value=model.value,
            unit=model.unit,
            condition_text=(
                model.condition_text
            ),
            section_id=(
                model.section_id
            ),
            section_version_id=(
                model.section_version_id
            ),
            status=(
                StaticThresholdStatus(
                    model.status
                )
            ),
            is_current=(
                model.is_current
            ),
            verified_at=(
                model.verified_at
            ),
            created_at=(
                model.created_at
            ),
            updated_at=(
                model.updated_at
            ),
        )