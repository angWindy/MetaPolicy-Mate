"""Real integration tests for P-234 backend.

Per plan rule §1 (conda ``p234``, real services), every test runs against
the live FastAPI app wired through ``ASGITransport`` with Postgres /
Redis / Qdrant / R2 already configured via ``.env`` and ``.env.rag``.

These tests replace the previous mock-based tests that targeted the
legacy ``src/api/routes.py`` contract; the production code now lives
under ``src/presentation/api/`` (clean architecture) and is exercised
through ``httpx.AsyncClient`` exactly as a real frontend would call it.

Run from the project root inside conda ``p234``:

    pytest tests/test_integration/ -v
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
import time
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PDF = PROJECT_ROOT / "data" / "raw" / "HUST" / "10232.pdf"

BACKEND_BASE = os.environ.get("BACKEND_BASE", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def http():
    async with httpx.AsyncClient(
        base_url=BACKEND_BASE,
        timeout=httpx.Timeout(180.0),
    ) as client:
        yield client


async def _login(
    client: httpx.AsyncClient,
    email: str,
    password: str = "P234@123",
) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": f"pytest-{secrets.token_hex(4)}",
        },
    )
    assert r.status_code == 200, (
        f"login failed: {r.status_code} {r.text[:300]}"
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health(http: httpx.AsyncClient) -> None:
    r = await http.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auth — login as the seeded admin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_admin_returns_token(http: httpx.AsyncClient) -> None:
    token = await _login(http, "admin@p234.demo")
    assert token and len(token) > 50


@pytest.mark.asyncio
async def test_login_invalid_password_rejected(
    http: httpx.AsyncClient,
) -> None:
    r = await http.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@p234.demo",
            "password": "wrong-password",
            "device_id": "pytest-bad",
        },
    )
    assert r.status_code in (400, 401, 403, 409)


# ---------------------------------------------------------------------------
# Document round-trip — upload, view, delete against real R2 + Postgres
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_view_delete_roundtrip(
    http: httpx.AsyncClient,
) -> None:
    if not DEFAULT_PDF.exists():
        pytest.skip(f"PDF fixture missing: {DEFAULT_PDF}")

    token = await _login(http, "admin@p234.demo")
    pdf_bytes = DEFAULT_PDF.read_bytes()
    sha_upload = hashlib.sha256(pdf_bytes).hexdigest()

    document_number = f"INT-{sha_upload[:8]}-{int(time.time())}"
    upload = await http.post(
        "/api/v1/regulatory-documents/upload",
        headers=_auth(token),
        data={
            "document_number": document_number,
            "title": "Integration test PDF",
            "issued_by": "Pytest",
            "issued_date": "2026-08-31",
            "effective_date": "2026-08-31",
            "access_scope": "public",
        },
        files={
            "file": (
                DEFAULT_PDF.name,
                pdf_bytes,
                "application/pdf",
            ),
        },
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    try:
        # Inline view (default).
        source = await http.get(
            f"/api/v1/regulatory-documents/{document_id}/source",
            headers=_auth(token),
        )
        assert source.status_code == 200, source.text
        assert source.headers.get("content-type", "").startswith(
            "application/pdf"
        )
        sha_download = hashlib.sha256(source.content).hexdigest()
        assert sha_download == sha_upload

        # Content-Disposition must always be present so a frontend can
        # detect the file name; the backend currently only exposes the
        # inline form (no separate attachment endpoint) and that is the
        # surface the rest of the app relies on.
        cd = source.headers.get("content-disposition", "")
        assert "inline" in cd.lower()
        assert DEFAULT_PDF.name in cd
    finally:
        cleanup = await http.delete(
            f"/api/v1/regulatory-documents/{document_id}",
            headers=_auth(token),
        )
        assert cleanup.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Auto-digitize — upload with auto_digitize=True exercises the RAG pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_with_auto_digitize_persists_chunks(
    http: httpx.AsyncClient,
) -> None:
    if not DEFAULT_PDF.exists():
        pytest.skip(f"PDF fixture missing: {DEFAULT_PDF}")

    token = await _login(http, "admin@p234.demo")
    pdf_bytes = DEFAULT_PDF.read_bytes()
    document_number = (
        f"INT-AUTODIG-{int(time.time())}"
    )

    upload = await http.post(
        "/api/v1/regulatory-documents/upload",
        headers=_auth(token),
        data={
            "document_number": document_number,
            "title": "Auto-digitize integration test",
            "issued_by": "Pytest",
            "issued_date": "2026-08-31",
            "effective_date": "2026-08-31",
            "access_scope": "public",
            "auto_digitize": "true",
        },
        files={
            "file": (
                DEFAULT_PDF.name,
                pdf_bytes,
                "application/pdf",
            ),
        },
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    try:
        # The pipeline is dispatched in the background after the upload
        # response returns. Poll the digitize-status endpoint until it
        # reports a terminal status (SUCCEEDED or FAILED).
        version_id: UUID | None = None
        terminal = False
        for _ in range(60):
            await asyncio.sleep(5)
            # Probe Postgres directly via psycopg v3 (already a
            # dependency for the FastAPI backend, no new package
            # required).
            import psycopg

            dsn = os.environ.get(
                "DATABASE_URL",
                "",
            ).replace(
                "postgresql+psycopg://",
                "postgresql://",
            )
            if not dsn:
                dsn = (
                    "postgresql://neondb_owner:npg_3KGSOat8TQHF@"
                    "ep-divine-credit-b3nynnck-pooler.c-4.ap-southeast-1."
                    "aws.neon.tech/p234?sslmode=require"
                )
            with psycopg.connect(dsn) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, processing_status "
                        "FROM public.document_versions "
                        "WHERE document_id = %s",
                        (document_id,),
                    )
                    row = cur.fetchone()
                    assert row is not None, (
                        "no version row found for uploaded doc"
                    )
                    version_id = row[0]
                    cur.execute(
                        "SELECT status, chunk_count "
                        "FROM public.document_ingestion_jobs "
                        "WHERE version_id = %s "
                        "ORDER BY started_at DESC LIMIT 1",
                        (version_id,),
                    )
                    row2 = cur.fetchone()
                    if row2 and row2[0] in ("SUCCEEDED", "FAILED"):
                        assert row2[0] == "SUCCEEDED", (
                            f"auto_digitize failed: status={row2[0]}"
                        )
                        assert row2[1] > 0, (
                            "auto_digitize reported 0 chunks"
                        )
                        terminal = True
                        break
        assert terminal, (
            "auto_digitize did not terminate within 5 minutes"
        )
    finally:
        cleanup = await http.delete(
            f"/api/v1/regulatory-documents/{document_id}",
            headers=_auth(token),
        )
        assert cleanup.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Chat — session/turn persistence + ACL re-check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_session_persists_across_turns(
    http: httpx.AsyncClient,
) -> None:
    token = await _login(http, "admin@p234.demo")
    headers = _auth(token)

    r1 = await http.post(
        "/api/v1/chat",
        json={"message": "Quy định đào tạo?"},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert "session_id" in body1
    assert "turn_id" in body1
    session_id = body1["session_id"]

    r2 = await http.post(
        "/api/v1/chat",
        json={
            "message": "Còn quy định nào khác không?",
            "session_id": session_id,
        },
        headers=headers,
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    # Continuation must reuse the same session.
    assert body2["session_id"] == session_id
    assert body2["turn_id"] != body1["turn_id"]


@pytest.mark.asyncio
async def test_chat_empty_message_rejected(
    http: httpx.AsyncClient,
) -> None:
    token = await _login(http, "admin@p234.demo")
    r = await http.post(
        "/api/v1/chat",
        json={"message": ""},
        headers=_auth(token),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# RBAC — anonymous request rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_cannot_list_documents(
    http: httpx.AsyncClient,
) -> None:
    r = await http.get("/api/v1/regulatory-documents")
    assert r.status_code in (401, 403)