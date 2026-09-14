"""Pytest round-trip for PDF upload -> view using FastAPI TestClient.

Marks: ``requires_rag_runtime`` so it's only run when the full stack
(Neon + Qdrant + Redis) is available.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import pytest_asyncio


pytestmark = pytest.mark.requires_rag_runtime


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PDF = PROJECT_ROOT / "data" / "raw" / "HUST" / "10232.pdf"


def _login_payload() -> dict[str, str]:
    return {
        "email": "admin@p234.demo",
        "password": "P234@123",
        "device_id": "pytest-pdf-roundtrip",
    }


@pytest.mark.asyncio
async def test_pdf_upload_and_view_roundtrip(client) -> None:
    """Login as admin, upload a real PDF, GET it back, verify SHA256."""
    if not DEFAULT_PDF.exists():
        pytest.skip(f"PDF fixture missing: {DEFAULT_PDF}")

    pdf_bytes = DEFAULT_PDF.read_bytes()
    sha_upload = hashlib.sha256(pdf_bytes).hexdigest()

    login = await client.post(
        "/api/v1/auth/login",
        json=_login_payload(),
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    document_number = f"PYTEST-PDF-{sha_upload[:8]}"
    upload = await client.post(
        "/api/v1/regulatory-documents/upload",
        headers=headers,
        data={
            "document_number": document_number,
            "title": "Pytest PDF roundtrip",
            "issued_by": "Pytest",
            "issued_date": "2026-08-28",
            "effective_date": "2026-08-28",
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
        source = await client.get(
            f"/api/v1/regulatory-documents/{document_id}/source",
            headers=headers,
        )
        assert source.status_code == 200, source.text
        content_type = source.headers.get("Content-Type", "")
        assert content_type.startswith("application/pdf"), (
            f"unexpected content type {content_type!r}"
        )
        sha_download = hashlib.sha256(source.content).hexdigest()
        assert sha_download == sha_upload, (
            "downloaded PDF body does not match upload"
        )
    finally:
        # Best-effort DB cleanup so the test is idempotent.
        try:
            import psycopg  # noqa: PLC0415

            conn = psycopg.connect(
                "postgresql://neondb_owner:"
                "npg_AKDtQliGzj63"
                "@ep-proud-base-a70h0gom-pooler."
                "ap-southeast-2.aws.neon.tech/p234_uc_demo"
                "?sslmode=require",
                connect_timeout=10,
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SET search_path TO public, rag_legacy"
                )
                cur.execute(
                    "DELETE FROM documents WHERE id = %s::uuid",
                    (document_id,),
                )
            conn.commit()
            conn.close()
        except Exception:  # noqa: BLE001
            pass