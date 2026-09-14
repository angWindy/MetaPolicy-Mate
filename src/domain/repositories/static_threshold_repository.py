from typing import Protocol
from uuid import UUID

from src.domain.entities.static_threshold import (
    StaticThreshold,
)


class StaticThresholdRepository(
    Protocol
):
    async def get_by_id(
        self,
        threshold_id: UUID,
    ) -> StaticThreshold | None:
        ...

    async def get_history(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> list[StaticThreshold]:
        ...

    async def get_current(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> StaticThreshold | None:
        ...

    async def get_verified_current(
        self,
    ) -> list[StaticThreshold]:
        ...

    async def get_next_version_number(
        self,
        threshold_key: str,
        scope_key: str,
    ) -> int:
        ...

    async def add(
        self,
        threshold: StaticThreshold,
    ) -> None:
        ...

    async def update(
        self,
        threshold: StaticThreshold,
    ) -> None:
        ...