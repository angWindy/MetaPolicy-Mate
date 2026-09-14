"""Shared pytest fixtures for the P-234 backend test suite.

Per plan rule §1, every test runs against the live FastAPI app via
``httpx.AsyncClient`` with Postgres / Redis / Qdrant / R2 already
configured through ``.env`` and ``.env.rag``. No transport-layer
mocking is allowed; fixtures below hit real services only.
"""

from httpx import (
    ASGITransport,
    AsyncClient,
)

import pytest
import pytest_asyncio

from src.main import app


@pytest_asyncio.fixture
async def client():
    """Async HTTP client against the real FastAPI app.

    Hits the live ASGI app — no mocking at the transport layer.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
