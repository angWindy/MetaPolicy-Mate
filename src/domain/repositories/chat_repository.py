from typing import Protocol
from uuid import UUID

from src.domain.entities.chat_session import (
    ChatSession,
)
from src.domain.entities.chat_turn import (
    ChatTurn,
)


class ChatRepository(
    Protocol
):
    async def get_session(
        self,
        session_id: UUID,
    ) -> ChatSession | None:
        ...

    async def list_sessions(
        self,
        user_id: UUID,
    ) -> list[ChatSession]:
        """List all sessions for a user, ordered by updated_at desc."""
        ...

    async def add_session(
        self,
        session: ChatSession,
    ) -> None:
        ...

    async def update_session(
        self,
        session: ChatSession,
    ) -> None:
        ...

    async def delete_session(
        self,
        session_id: UUID,
    ) -> None:
        """Delete a session and all its turns."""
        ...

    async def list_turns(
        self,
        session_id: UUID,
    ) -> list[ChatTurn]:
        ...

    async def add_turn(
        self,
        turn: ChatTurn,
    ) -> None:
        ...

    async def get_turn(
        self,
        turn_id: UUID,
    ) -> ChatTurn | None:
        ...

    async def count_turns(
        self,
    ) -> int:
        ...

    async def count_turns_in_session(
        self,
        session_id: UUID,
    ) -> int:
        """Count turns in a specific session."""
        ...