from typing import Protocol
from uuid import UUID


class TenantDatabaseProvider(Protocol):
    async def get_database_url(
        self,
        school_id: UUID,
    ) -> str:
        ...