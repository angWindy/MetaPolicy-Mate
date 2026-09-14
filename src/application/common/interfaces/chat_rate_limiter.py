from typing import Protocol
from uuid import UUID


class ChatRateLimiter(
    Protocol
):
    async def check(
        self,
        user_id: UUID,
    ) -> tuple[
        bool,
        int,
    ]:
        """
        Returns:
            allowed,
            retry_after_seconds
        """
        ...

    async def check_key(
        self,
        *,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[
        bool,
        int,
    ]:
        ...

    async def acquire_lock(
        self,
        user_id: UUID,
    ) -> str | None:
        ...

    async def release_lock(
        self,
        user_id: UUID,
        token: str,
    ) -> None:
        ...