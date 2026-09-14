from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.domain.entities.user_activity_log import (
    UserActivityLog,
)


class UserActivityLogRepository(
    Protocol
):
    async def add(
        self,
        log: UserActivityLog,
    ) -> None:
        ...

    async def get_by_id(
        self,
        log_id: UUID,
    ) -> UserActivityLog | None:
        ...

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
        ...