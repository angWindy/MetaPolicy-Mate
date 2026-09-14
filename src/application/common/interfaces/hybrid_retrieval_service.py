from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class HybridRetrievalActor:
    user_id: UUID

    department: str

    roles: set[str]


@dataclass(frozen=True)
class HybridRetrievalItem:
    chunk_id: str

    text: str

    score: float

    source: str

    metadata: dict


class HybridRetrievalService(
    Protocol
):
    async def search(
        self,
        *,
        query: str,
        actor: HybridRetrievalActor,
        as_of_date: date | None,
        embed_text: str | None = None,
    ) -> list[
        HybridRetrievalItem
    ]:
        ...