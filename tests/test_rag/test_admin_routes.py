"""Admin routes tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from src.api.routes import get_rag_request_context
from src.main import app
from src.security.policy import AuthenticatedIdentity


@dataclass
class _StubVersion:
    id: str = "v1"
    processing_status: str = "approved"
    approved_by: str = "owner"
    legal_status: str = "effective"


@dataclass
class _StubRepository:
    approve_calls: list = None
    publish_calls: list = None
    publish_should_raise: Exception | None = None

    def __post_init__(self):
        self.approve_calls = []
        self.publish_calls = []

    def approve_version(self, version_id, approved_by):
        self.approve_calls.append((version_id, approved_by))
        return _StubVersion()

    def publish_version(self, version_id):
        self.publish_calls.append(version_id)
        if self.publish_should_raise is not None:
            raise self.publish_should_raise
        v = _StubVersion()
        v.processing_status = "published"
        v.legal_status = "effective"
        return v

    def refresh_current_legal_statuses(self):
        return None

    def stats(self):
        return {"documents": 1, "versions": 2, "chunks": 3}


@dataclass
class _StubContainer:
    repository: _StubRepository
    warm_index_called: int = 0
    index_calls: list = None
    ingestion_index_should_raise: Exception | None = None

    def __post_init__(self):
        self.index_calls = []

    async def warm_index(self) -> int:
        self.warm_index_called += 1
        return 7

    @property
    def ingestion(self):
        outer = self

        class _StubIngestion:
            async def index_approved_version(self_inner, version_id):
                outer.index_calls.append(version_id)
                if outer.ingestion_index_should_raise is not None:
                    raise outer.ingestion_index_should_raise
                return 5

        return _StubIngestion()


def _context(roles=("data_owner",)):
    identity = AuthenticatedIdentity(
        user_id="owner-1", tenant_id="hust", department="TCCB", assigned_roles=frozenset(roles)
    )
    container = _StubContainer(repository=_StubRepository())
    return type("Ctx", (), {"identity": identity, "container": container})()


@pytest.fixture
def client():
    return TestClient(app)


def test_approve_requires_data_owner_role(client):
    ctx = _context(roles=("staff",))
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/approve")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_approve_succeeds_for_data_owner(client):
    ctx = _context()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/approve")
        assert response.status_code == 200
        assert ctx.container.repository.approve_calls == [("v1", "owner-1")]
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_publish_succeeds_for_data_owner(client):
    ctx = _context()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/publish")
        assert response.status_code == 200
        assert ctx.container.repository.publish_calls == ["v1"]
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_publish_blocked_when_repository_rejects_unindexed_state(client):
    """Repository now raises ValueError if status is not INDEXED; route must surface 400."""
    ctx = _context()
    ctx.container.repository.publish_should_raise = ValueError(
        "Phiên bản phải được duyệt (approved) rồi tạo vector trong Qdrant (indexed) "
        "trước khi xuất bản. Hiện tại: processing_status=approved."
    )
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/publish")
        assert response.status_code == 400
        assert "indexed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_index_endpoint_indexes_approved_version(client):
    ctx = _context()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/index")
        assert response.status_code == 200
        body = response.json()
        assert body["version_id"] == "v1"
        assert body["processing_status"] == "indexed"
        assert body["indexed_chunks"] == 5
        assert ctx.container.index_calls == ["v1"]
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_index_endpoint_returns_502_when_indexing_fails(client):
    """If Qdrant fails mid-flight, the API must respond 502 and the status
    stays at APPROVED so the operator can retry."""
    ctx = _context()
    ctx.container.ingestion_index_should_raise = RuntimeError(
        "Index thất bại cho version_id=v1. "
        "Phiên bản vẫn ở trạng thái APPROVED để retry. Lỗi: ConnectionError: qdrant down"
    )
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/documents/v1/index")
        assert response.status_code == 502
        body = response.json()
        assert "APPROVED" in body["detail"]
        assert "qdrant down" in body["detail"]
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_reindex_refreshes_and_warms(client):
    ctx = _context()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.post("/api/v1/admin/index/reindex")
        assert response.status_code == 200
        assert response.json() == {"indexed_chunks": 7}
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_stats(client):
    ctx = _context()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    try:
        response = client.get("/api/v1/admin/stats")
        assert response.status_code == 200
        assert response.json()["documents"] == 1
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)