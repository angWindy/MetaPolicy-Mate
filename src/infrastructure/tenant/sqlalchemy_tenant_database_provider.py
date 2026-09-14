from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.common.tenant.tenant_database_provider import (
    TenantDatabaseProvider as TenantDatabaseProviderProtocol,
)
from src.persistence.master.configurations.school_configuration import (
    schools,
)


class SqlAlchemyTenantDatabaseProvider(
    TenantDatabaseProviderProtocol
):
    def __init__(
        self,
        master_session: AsyncSession,
    ) -> None:
        self._master_session = master_session

    async def get_database_url(
        self,
        school_id: UUID,
    ) -> str:
        result = await self._master_session.execute(
            select(
                schools.c.DatabaseUrl
            ).where(
                schools.c.Id == school_id,
                schools.c.IsActive.is_(True),
            )
        )

        database_url = result.scalar_one_or_none()

        if database_url is None:
            raise ValueError(
                "Tenant database not found "
                f"for school {school_id}"
            )

        return str(database_url)