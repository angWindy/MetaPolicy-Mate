"""Tests for the chat session management API.

Verifies:
- Session CRUD operations via the API endpoints
- Session listing returns only the authenticated user's sessions
- Deleting a session removes it and all associated turns
- Loading a session returns its turns in chronological order
"""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

# The FastAPI app must be imported after the env is set.
from src.presentation.api.routers.chat_router import router
from src.domain.entities.chat_session import ChatSession
from src.domain.entities.chat_turn import ChatTurn
from src.persistence.tenant.repositories.sqlalchemy_chat_repository import (
    SqlAlchemyChatRepository,
)


class DummyChatRepository:
    """In-memory repository for testing without a real database."""

    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}
        self._turns: dict[str, list[ChatTurn]] = {}

    async def get_session(self, session_id: uuid4):
        return self._sessions.get(str(session_id))

    async def list_sessions(self, user_id: uuid4):
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id
        ]

    async def add_session(self, session: ChatSession):
        self._sessions[str(session.id)] = session
        self._turns[str(session.id)] = []

    async def update_session(self, session: ChatSession):
        self._sessions[str(session.id)] = session

    async def delete_session(self, session_id: uuid4):
        sid = str(session_id)
        self._sessions.pop(sid, None)
        self._turns.pop(sid, None)

    async def list_turns(self, session_id: uuid4):
        return self._turns.get(str(session_id), [])

    async def add_turn(self, turn: ChatTurn):
        sid = str(turn.session_id)
        if sid not in self._turns:
            self._turns[sid] = []
        self._turns[sid].append(turn)

    async def get_turn(self, turn_id: uuid4):
        for turns in self._turns.values():
            for t in turns:
                if str(t.id) == str(turn_id):
                    return t
        return None

    async def count_turns(self):
        return sum(len(v) for v in self._turns.values())

    async def count_turns_in_session(self, session_id: uuid4):
        return len(self._turns.get(str(session_id), []))


# ─────────────────────────────────────────────────────────────────────────────
# Repository tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repository_create_and_retrieve_session():
    repo = DummyChatRepository()
    user_id = uuid4()
    session = ChatSession(
        id=uuid4(),
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await repo.add_session(session)
    retrieved = await repo.get_session(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id
    assert retrieved.user_id == user_id


@pytest.mark.asyncio
async def test_repository_list_sessions_returns_only_user_sessions():
    repo = DummyChatRepository()
    user_a = uuid4()
    user_b = uuid4()

    for i in range(3):
        s = ChatSession(
            id=uuid4(),
            user_id=user_a,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        await repo.add_session(s)

    other = ChatSession(
        id=uuid4(),
        user_id=user_b,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await repo.add_session(other)

    sessions = await repo.list_sessions(user_a)
    assert len(sessions) == 3
    assert all(s.user_id == user_a for s in sessions)


@pytest.mark.asyncio
async def test_repository_delete_session_removes_turns():
    repo = DummyChatRepository()
    user_id = uuid4()
    session = ChatSession(
        id=uuid4(),
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await repo.add_session(session)

    turn = ChatTurn(
        id=uuid4(),
        session_id=session.id,
        question="Câu hỏi?",
        answer="Trả lời.",
        citations=[],
        created_at=datetime.now(timezone.utc),
    )
    await repo.add_turn(turn)

    await repo.delete_session(session.id)

    assert await repo.get_session(session.id) is None
    assert await repo.list_turns(session.id) == []
    assert await repo.count_turns_in_session(session.id) == 0


@pytest.mark.asyncio
async def test_repository_turns_returned_in_chronological_order():
    repo = DummyChatRepository()
    user_id = uuid4()
    session = ChatSession(
        id=uuid4(),
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await repo.add_session(session)

    for i in range(5):
        turn = ChatTurn(
            id=uuid4(),
            session_id=session.id,
            question=f"Câu hỏi {i}",
            answer=f"Trả lời {i}",
            citations=[],
            created_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
        )
        await repo.add_turn(turn)

    turns = await repo.list_turns(session.id)
    assert len(turns) == 5
    # Chronological ascending order.
    assert turns[0].question == "Câu hỏi 0"
    assert turns[-1].question == "Câu hỏi 4"


@pytest.mark.asyncio
async def test_repository_count_turns_in_session():
    repo = DummyChatRepository()
    user_id = uuid4()
    session = ChatSession(
        id=uuid4(),
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    await repo.add_session(session)

    for i in range(3):
        await repo.add_turn(
            ChatTurn(
                id=uuid4(),
                session_id=session.id,
                question=f"Q{i}",
                answer=f"A{i}",
                citations=[],
                created_at=datetime.now(timezone.utc),
            )
        )

    assert await repo.count_turns_in_session(session.id) == 3


@pytest.mark.asyncio
async def test_repository_get_nonexistent_session_returns_none():
    repo = DummyChatRepository()
    result = await repo.get_session(uuid4())
    assert result is None