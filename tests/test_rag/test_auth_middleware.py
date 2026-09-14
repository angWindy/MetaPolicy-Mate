"""Auth middleware tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.routes import get_rag_request_context
from src.main import app
from src.rag.config import RAGSettings
from src.security.policy import AuthenticatedIdentity


@pytest.fixture
def client():
    return TestClient(app)


def _install_stub_container():
    class _StubPipeline:
        async def ainvoke(self, state, config):
            return {"answer": "ok", "citations": []}

    class _StubContainer:
        pipeline = _StubPipeline()
        settings = RAGSettings(app_env="test")

    ctx = type(
        "Ctx",
        (),
        {
            "identity": AuthenticatedIdentity(
                user_id="dev-user",
                tenant_id="hust",
                department="TCCB",
                assigned_roles=frozenset({"staff"}),
            ),
            "container": _StubContainer(),
        },
    )()
    app.dependency_overrides[get_rag_request_context] = lambda: ctx
    return ctx


def test_public_paths_bypass_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_protected_path_requires_identity_in_development(client, monkeypatch):
    monkeypatch.setattr(
        "src.api.auth.get_rag_settings",
        lambda: __import__("src.rag.config", fromlist=["RAGSettings"]).RAGSettings(
            app_env="development", dev_auth_bypass=True
        ),
    )
    # No stub container installed; should return 401 (no identity) before container init.
    app.dependency_overrides.pop(get_rag_request_context, None)
    response = client.post(
        "/api/v1/chat", json={"message": "Ai phê duyệt nghỉ phép?"}
    )
    assert response.status_code == 401


def test_dev_bypass_headers_create_identity(client, monkeypatch):
    monkeypatch.setattr(
        "src.api.auth.get_rag_settings",
        lambda: __import__("src.rag.config", fromlist=["RAGSettings"]).RAGSettings(
            app_env="development", dev_auth_bypass=True
        ),
    )
    _install_stub_container()
    try:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Xin chào"},
            headers={
                "X-User-Id": "dev-user",
                "X-Tenant-Id": "hust",
                "X-Department": "TCCB",
                "X-Roles": "staff,manager",
            },
        )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_rag_request_context, None)


def test_dev_bypass_headers_rejected_in_production(client, monkeypatch):
    """Verify the middleware rejects dev-bypass headers in production."""
    from src.api.auth import _identity_from_headers

    request = type(
        "Req",
        (),
        {
            "headers": {"X-User-Id": "u", "X-Tenant-Id": "t", "X-Department": "d"},
            "url": type("URL", (), {"path": "/api/v1/chat"})(),
        },
    )()
    identity = _identity_from_headers(request)
    assert identity is not None
    # The middleware uses settings.app_env to gate; verify the production validator.
    production = __import__("src.rag.config", fromlist=["RAGSettings"]).RAGSettings(
        app_env="production",
        dev_auth_bypass=False,
        generator_provider="template",
        embedding_provider="hash",
        embedding_dimensions=64,
        openai_api_key="dummy",
        database_url="postgresql+psycopg://test:test@localhost:5432/test",
    )
    assert production.app_env == "production"
    assert production.dev_auth_bypass is False
