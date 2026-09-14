from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RagChatActor:
    user_id: UUID

    department: str

    roles: set[str]


@dataclass(frozen=True)
class RagChatResult:
    answer: str

    citations: list[dict]

    warnings: list[str]

    confidence: str


class RagChatService(
    Protocol
):
    async def answer(
        self,
        *,
        question: str,
        retrieval_query: str,
        actor: RagChatActor,
        conversation_context: str = "",
    ) -> RagChatResult:
        ...
