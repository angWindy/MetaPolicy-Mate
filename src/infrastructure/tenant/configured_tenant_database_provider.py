from uuid import UUID

from src.application.common.tenant.tenant_database_provider import (
    TenantDatabaseProvider,
)


class ConfiguredTenantDatabaseProvider(
    TenantDatabaseProvider
):
    def __init__(
        self,
        school_id: UUID,
        database_url: str,
    ) -> None:
        self._school_id = school_id
        self._database_url = database_url

    async def get_database_url(
        self,
        school_id: UUID,
    ) -> str:
        if school_id != self._school_id:
            raise ValueError(
                f"Unknown school: {school_id}"
            )

        return self._database_url