from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)


class SqlAlchemyUnitOfWork(
    UnitOfWork
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def flush(
        self,
    ) -> None:
        await self._session.flush()

    async def save_changes(
        self,
    ) -> None:
        await self._session.commit()

    async def rollback(
        self,
    ) -> None:
        await self._session.rollback()