from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.user_activity_log import (
    UserActivityLog,
)
from src.domain.repositories.user_activity_log_repository import (
    UserActivityLogRepository,
)
from src.persistence.tenant.models.user_activity_log import (
    UserActivityLogModel,
)


class SqlAlchemyUserActivityLogRepository(
    UserActivityLogRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        log: UserActivityLog,
    ) -> None:
        self._session.add(
            UserActivityLogModel(
                id=log.id,
                school_id=log.school_id,
                user_id=log.user_id,
                request_name=(
                    log.request_name
                ),
                status=log.status,
                trace_id=log.trace_id,
                ip_address=(
                    log.ip_address
                ),
                device_id=log.device_id,
                user_agent=log.user_agent,
                error_message=(
                    log.error_message
                ),
                started_at=log.started_at,
                completed_at=(
                    log.completed_at
                ),
            )
        )

    async def get_by_id(
        self,
        log_id: UUID,
    ) -> UserActivityLog | None:
        model = await self._session.get(
            UserActivityLogModel,
            log_id,
        )

        if model is None:
            return None

        return self._to_domain(model)

    async def get_list(
        self,
        *,
        user_id: UUID | None,
        request_name: str | None,
        status: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[
        list[UserActivityLog],
        int,
    ]:
        conditions = []

        if user_id is not None:
            conditions.append(
                UserActivityLogModel
                .user_id
                == user_id
            )

        if (
            request_name
            and request_name.strip()
        ):
            conditions.append(
                UserActivityLogModel
                .request_name
                .ilike(
                    "%"
                    + request_name.strip()
                    + "%"
                )
            )

        if status:
            conditions.append(
                UserActivityLogModel
                .status
                == status.strip()
            )

        if from_at is not None:
            conditions.append(
                UserActivityLogModel
                .started_at
                >= from_at
            )

        if to_at is not None:
            conditions.append(
                UserActivityLogModel
                .started_at
                <= to_at
            )

        count_statement = (
            select(
                func.count(
                    UserActivityLogModel.id
                )
            )
        )

        if conditions:
            count_statement = (
                count_statement.where(
                    *conditions
                )
            )

        total_result = await (
            self._session.execute(
                count_statement
            )
        )

        total = int(
            total_result.scalar_one()
            or 0
        )

        statement = select(
            UserActivityLogModel
        )

        if conditions:
            statement = statement.where(
                *conditions
            )

        statement = (
            statement
            .order_by(
                UserActivityLogModel
                .started_at
                .desc()
            )
            .offset(
                (page - 1)
                * page_size
            )
            .limit(page_size)
        )

        result = await (
            self._session.execute(
                statement
            )
        )

        items = [
            self._to_domain(model)
            for model
            in result.scalars().all()
        ]

        return items, total

    @staticmethod
    def _to_domain(
        model: UserActivityLogModel,
    ) -> UserActivityLog:
        return UserActivityLog(
            id=model.id,
            school_id=model.school_id,
            user_id=model.user_id,
            request_name=(
                model.request_name
            ),
            status=model.status,
            trace_id=model.trace_id,
            ip_address=(
                model.ip_address
            ),
            device_id=model.device_id,
            user_agent=model.user_agent,
            error_message=(
                model.error_message
            ),
            started_at=model.started_at,
            completed_at=(
                model.completed_at
            ),
        )