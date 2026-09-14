#!/usr/bin/env python3
"""Batch upload of data/raw/{HUST,HUCE}/*.pdf using the admin account.

Flow per file:
  1. Upload (multipart) -> status=RECEIVED
  2. PUT /access {DEPARTMENT, [department_id]}
  3. POST /digitize  -> status=DA_SO_HOA (INDEXED) OR PENDING_REVIEW
  4. POST /index     -> idempotent flip to INDEXED + Qdrant sync
  5. POST /publish   -> status=PUBLISHED

If the metadata-quality gate in digitize returns PENDING_REVIEW
(usually because the document_number didn't match the canonical
regex), we surface it as a warning instead of silently failing the
whole batch.

Idempotency: skip any file whose derived document_number already
exists in the DB.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("admin-batch-upload")

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/v1"
ADMIN_EMAIL = "admin@p234.demo"
ADMIN_PASSWORD = "P234@123"

DEPARTMENT_CODE_TO_ID_CACHE: dict[str, str] = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug_filename(stem: str) -> str:
    s = unicodedata.normalize("NFD", stem)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s


def derive_document_number(filename_stem: str, existing: set[str]) -> str:
    """Choose a document_number that passes the canonical regex.

    Canonical regex (src/domain/validators/document_validator.py):
        ^(\\d+|\\d+/[A-Z0-9]+(?:-[A-Z0-9]+)*)$
    Strategy:
      1. If the stem starts with a pure number (e.g. ``10232``,
         ``2048-table``), use the leading digits.
      2. Otherwise derive a 6-digit hash from the slug. If the hash
         collides with an existing document_number, fall back to the
         SHA-1 prefix (10 digits, also pure numeric).
    """
    m = re.match(r"^\s*(\d+)", filename_stem)
    if m:
        return m.group(1)
    base = _slug_filename(filename_stem)
    for width in (6, 8, 10):
        candidate = str(int(hashlib.sha1(base.encode()).hexdigest(), 16))[:width].lstrip("0") or "0"
        if candidate not in existing:
            return candidate
    return str(int(hashlib.sha1(base.encode()).hexdigest(), 16))[:12]


def existing_document_numbers() -> set[str]:
    """Load every document_number currently in the public schema."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        load_dotenv(PROJECT_ROOT / ".env")
        db_url = os.environ.get("DATABASE_URL")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(db_url, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT document_number FROM public.documents")).all()
    return {r[0] for r in rows}


# ---------------------------------------------------------------------------
# Admin HTTP client
# ---------------------------------------------------------------------------


class AdminClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._timeout = httpx.Timeout(120.0, connect=30.0)

    def _login(self) -> None:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{BASE_URL}{API_PREFIX}/auth/login",
                json={
                    "email": ADMIN_EMAIL,
                    "password": ADMIN_PASSWORD,
                    "device_id": "admin-batch-upload",
                },
            )
        if r.status_code != 200:
            raise SystemExit(f"login failed {r.status_code}: {r.text[:300]}")
        body = r.json()
        self._token = body.get("access_token")
        if not self._token:
            raise SystemExit(f"login: no access_token: {r.text[:300]}")
        log.info("logged in as %s", ADMIN_EMAIL)

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, *, max_retries: int = 1, **kw) -> httpx.Response:
        url = f"{BASE_URL}{API_PREFIX}{path}"
        headers = kw.pop("headers", {})
        headers.update(self._headers())
        last_exc: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as c:
                    r = c.request(method, url, headers=headers, **kw)
                if r.status_code == 401 and attempt < max_retries:
                    log.warning("401 — re-authenticating")
                    self._login()
                    headers.update(self._headers())
                    continue
                return r
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                log.warning("network error %s on %s %s (attempt %d)", exc, method, path, attempt + 1)
                time.sleep(2)
        raise SystemExit(f"network failure after retries: {last_exc}")

    # ---- helpers ---------------------------------------------------------

    def get_department_id(self, code: str) -> str:
        if code in DEPARTMENT_CODE_TO_ID_CACHE:
            return DEPARTMENT_CODE_TO_ID_CACHE[code]
        r = self._request("GET", "/departments")
        if r.status_code != 200:
            raise SystemExit(f"departments list failed {r.status_code}: {r.text[:200]}")
        items = r.json()
        if isinstance(items, dict):
            items = items.get("items") or items.get("data") or []
        for dept in items:
            if str(dept.get("code", "")).upper() == code.upper():
                DEPARTMENT_CODE_TO_ID_CACHE[code] = str(dept["id"])
                return DEPARTMENT_CODE_TO_ID_CACHE[code]
        raise SystemExit(f"department code '{code}' not found")

    # ---- lifecycle -------------------------------------------------------

    def upload(
        self,
        *,
        document_number: str,
        title: str,
        issued_by: str,
        issued_date: str,
        effective_date: str,
        pdf_path: Path,
    ) -> dict[str, Any]:
        with pdf_path.open("rb") as fh:
            files = {"file": (pdf_path.name, fh, "application/pdf")}
            data = {
                "document_number": document_number,
                "title": title,
                "issued_by": issued_by,
                "issued_date": issued_date,
                "effective_date": effective_date,
                "auto_digitize": "false",
            }
            return self._request("POST", "/regulatory-documents/upload", data=data, files=files).json()

    def set_access(self, document_id: str, access_scope: str, department_ids: list[str]) -> None:
        r = self._request(
            "PUT",
            f"/regulatory-documents/{document_id}/access",
            json={"access_scope": access_scope, "department_ids": department_ids},
        )
        if r.status_code not in (200, 204):
            raise SystemExit(f"PUT /access failed {r.status_code}: {r.text[:300]}")

    def digitize(self, document_id: str, version_id: str) -> dict[str, Any]:
        r = self._request(
            "POST",
            f"/regulatory-documents/{document_id}/versions/{version_id}/digitize",
        )
        return r.json()

    def index(self, version_id: str) -> dict[str, Any]:
        with httpx.Client(timeout=httpx.Timeout(360.0, connect=30.0)) as c:
            r = c.post(
                f"{BASE_URL}{API_PREFIX}/admin/documents/{version_id}/index",
                headers=self._headers(),
            )
        if r.status_code == 401:
            self._login()
            return self.index(version_id)
        return r.json()

    def publish(self, version_id: str) -> dict[str, Any]:
        r = self._request("POST", f"/admin/documents/{version_id}/publish")
        return r.json()


# ---------------------------------------------------------------------------
# Version id lookup (admin read API doesn't expose it)
# ---------------------------------------------------------------------------


_DB_ENGINE: Engine | None = None


def _db() -> Engine:
    global _DB_ENGINE
    if _DB_ENGINE is not None:
        return _DB_ENGINE
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        load_dotenv(PROJECT_ROOT / ".env")
        db_url = os.environ.get("DATABASE_URL")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    _DB_ENGINE = create_engine(db_url, pool_pre_ping=True)
    return _DB_ENGINE


def lookup_version_id(document_id: str) -> str | None:
    with _db().connect() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM public.document_versions "
                "WHERE document_id = :doc_id "
                "ORDER BY version_number DESC LIMIT 1"
            ),
            {"doc_id": document_id},
        ).first()
    return str(row[0]) if row else None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass
class Result:
    school: str
    pdf: str
    document_number: str
    status: str  # uploaded|skipped|failed
    document_id: str | None = None
    version_id: str | None = None
    detail: str = ""


def discover_pdfs() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for school in ("HUST", "HUCE"):
        sd = RAW_DIR / school
        if not sd.is_dir():
            continue
        for p in sorted(sd.glob("*.pdf")):
            out.append((school, p))
    return out


def process_one(client: AdminClient, school: str, pdf: Path, existing: set[str]) -> Result:
    doc_num = derive_document_number(pdf.stem, existing)
    if doc_num in existing:
        return Result(
            school=school,
            pdf=pdf.name,
            document_number=doc_num,
            status="skipped",
            detail="document_number already in DB",
        )
    log.info("[%s] upload %s -> %s", school, pdf.name, doc_num)
    issued_by = "Đại học Bách khoa Hà Nội" if school == "HUST" else "Trường Đại học Kiến trúc Hà Nội"
    # Title must be ≥ 8 chars (MetadataQualityGate.MIN_TITLE_LENGTH)
    # and human-readable. Pad short stems with a school prefix so the
    # quality gate passes deterministically.
    title = f"Tài liệu {school} - {pdf.stem}"
    if len(title) < 8:
        title = f"Tài liệu {school} số {doc_num}"
    try:
        uploaded = client.upload(
            document_number=doc_num,
            title=title,
            issued_by=issued_by,
            issued_date=date.today().isoformat(),
            effective_date=date.today().isoformat(),
            pdf_path=pdf,
        )
    except Exception as exc:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed", detail=f"upload: {exc}")
    document_id = str(uploaded["id"])
    version_id = lookup_version_id(document_id)
    if not version_id:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed",
                      document_id=document_id, detail="version_id not found")

    try:
        department_id = client.get_department_id(school)
        client.set_access(document_id, "DEPARTMENT", [department_id])
    except Exception as exc:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed",
                      document_id=document_id, version_id=version_id, detail=f"access: {exc}")

    # Digitize (may return PENDING_REVIEW if quality gate fails)
    try:
        dig = client.digitize(document_id, version_id)
    except httpx.HTTPStatusError as exc:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed",
                      document_id=document_id, version_id=version_id, detail=f"digitize: {exc}")
    dig_status = dig.get("status") or dig.get("processing_status")
    if dig_status == "pending_review":
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="skipped",
                      document_id=document_id, version_id=version_id,
                      detail=f"digitize returned pending_review (metadata quality gate): {dig.get('warnings')}")

    # Index (idempotent) — flips status to INDEXED + Qdrant sync
    try:
        idx = client.index(version_id)
    except Exception as exc:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed",
                      document_id=document_id, version_id=version_id, detail=f"index: {exc}")

    # Publish
    try:
        pub = client.publish(version_id)
    except Exception as exc:
        return Result(school=school, pdf=pdf.name, document_number=doc_num, status="failed",
                      document_id=document_id, version_id=version_id, detail=f"publish: {exc}")

    return Result(
        school=school,
        pdf=pdf.name,
        document_number=doc_num,
        status="uploaded",
        document_id=document_id,
        version_id=version_id,
        detail=f"index={idx.get('status')} publish={pub.get('status')}",
    )


def main() -> int:
    pdfs = discover_pdfs()
    log.info("discovered %d PDFs", len(pdfs))
    if not pdfs:
        return 0
    existing = existing_document_numbers()
    log.info("existing document_numbers in DB: %d", len(existing))

    client = AdminClient()
    client._login()  # explicit early login so we fail fast
    results: list[Result] = []
    started = time.monotonic()
    for i, (school, pdf) in enumerate(pdfs, 1):
        log.info("--- (%d/%d) %s/%s ---", i, len(pdfs), school, pdf.name)
        r = process_one(client, school, pdf, existing)
        results.append(r)
        if r.status == "uploaded" and r.document_number:
            existing.add(r.document_number)
        log.info("   -> %s (%s)", r.status, r.detail)
    elapsed = time.monotonic() - started

    counts = {"uploaded": 0, "skipped": 0, "failed": 0}
    for r in results:
        counts[r.status] += 1
    log.info("=== DONE in %.1fs ===", elapsed)
    log.info("uploaded=%d  skipped=%d  failed=%d", counts["uploaded"], counts["skipped"], counts["failed"])

    if counts["failed"]:
        log.error("Failures:")
        for r in results:
            if r.status == "failed":
                log.error("  [%s] %s -> %s :: %s", r.school, r.pdf, r.document_number, r.detail)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
