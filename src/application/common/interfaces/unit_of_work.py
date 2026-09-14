from typing import Protocol


class UnitOfWork(
    Protocol
):
    async def flush(
        self,
    ) -> None:
        ...

    async def save_changes(
        self,
    ) -> None:
        ...

    async def rollback(
        self,
    ) -> None:
        ...