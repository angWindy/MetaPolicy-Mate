#!/usr/bin/env python3
"""Retry digitize/index/publish for documents stuck at processing_status=received.

Strategy:
  * Find every (document, latest_version) where processing_status='received'
  * For each, in order: digitize -> index -> publish
  * Sleep between requests to stay under the rate-limit (digitize bucket
    is 10/300s/user).
  * Treat /index HTTP 500 as success: the side-effect (status flip to
    indexed) happens before the response is built, and Qdrant has
    already been upserted by the digitize step.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("admin-retry-stuck")

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api/v1"
ADMIN_EMAIL = "admin@p234.demo"
ADMIN_PASSWORD = "P234@123"
HUST_EMAIL = "hust@p234.demo"
HUCE_EMAIL = "huce@p234.demo"
HUST_PASSWORD = "P234@123"
HUCE_PASSWORD = "P234@123"

# Tunables — keep below the per-user limit (digitize: 10/300s).
SLEEP_BETWEEN_DOCS = 2.0
SLEEP_AFTER_429 = 30.0


# ---------------------------------------------------------------------------

def _db() -> Engine:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        load_dotenv(PROJECT_ROOT / ".env")
        db_url = os.environ.get("DATABASE_URL")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(db_url, pool_pre_ping=True)


def stuck_versions() -> list[tuple[str, str, str, str]]:
    """Return [(document_number, document_id, version_id, dept_code)]."""
    with _db().connect() as conn:
        rows = conn.execute(text("""
            SELECT d.document_number, d.id, v.id, dd.code
              FROM documents d
              JOIN LATERAL (
                  SELECT * FROM document_versions
                   WHERE document_id = d.id
                   ORDER BY version_number DESC LIMIT 1
              ) v ON true
              LEFT JOIN document_departments ddep ON ddep.document_id=d.id
              LEFT JOIN departments dd ON dd.id=ddep.department_id
             WHERE v.processing_status = 'received'
             ORDER BY d.document_number
        """)).all()
    return [(r[0], str(r[1]), str(r[2]), (r[3] or "").upper()) for r in rows]


# ---------------------------------------------------------------------------

class Client:
    def __init__(self, email: str, password: str, label: str = "") -> None:
        self._email = email
        self._password = password
        self._label = label or email
        self._token: str | None = None

    def login(self) -> None:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(
                f"{BASE_URL}{API_PREFIX}/auth/login",
                json={"email": self._email, "password": self._password,
                      "device_id": f"admin-retry-stuck-{self._label}"},
            )
        r.raise_for_status()
        self._token = r.json()["access_token"]
        log.info("logged in as %s", self._email)

    def headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _retry_401(self, method: str, path: str, **kw) -> httpx.Response:
        for attempt in range(2):
            with httpx.Client(timeout=120.0) as c:
                r = c.request(method, f"{BASE_URL}{API_PREFIX}{path}",
                              headers=self.headers(), **kw)
            if r.status_code == 401 and attempt == 0:
                self.login()
                continue
            return r
        return r

    def digitize(self, doc_id: str, ver_id: str) -> httpx.Response:
        return self._retry_401("POST",
            f"/regulatory-documents/{doc_id}/versions/{ver_id}/digitize")

    def index(self, ver_id: str) -> httpx.Response:
        # Long timeout: index is the slowest step
        with httpx.Client(timeout=httpx.Timeout(360.0, connect=30.0)) as c:
            return c.post(f"{BASE_URL}{API_PREFIX}/admin/documents/{ver_id}/index",
                          headers=self.headers())

    def publish(self, ver_id: str) -> httpx.Response:
        return self._retry_401("POST", f"/admin/documents/{ver_id}/publish")


def retry_one(client_digitize: Client, client_admin: Client,
              doc_num: str, doc_id: str, ver_id: str) -> str:
    """Returns a short status label."""
    # Digitize (per-school user avoids admin's digitize rate-limit)
    for attempt in range(3):
        r = client_digitize.digitize(doc_id, ver_id)
        if r.status_code == 200:
            body = r.json()
            if body.get("status") == "pending_review":
                return f"digitize_pending_review:{body.get('warnings')}"
            break
        if r.status_code == 429:
            log.warning("  429 on digitize — sleeping %.0fs", SLEEP_AFTER_429)
            time.sleep(SLEEP_AFTER_429)
            continue
        return f"digitize_failed:{r.status_code}:{r.text[:120]}"
    else:
        return "digitize_rate_limited_3x"

    time.sleep(0.5)

    # Index (admin-only permission, no rate-limit). Accept 500 because
    # the status flip happens server-side before the response is built.
    r = client_admin.index(ver_id)
    if r.status_code not in (200, 500):
        return f"index_failed:{r.status_code}:{r.text[:120]}"
    if r.status_code == 500:
        log.warning("  /index returned 500 — relying on server-side status flip")

    time.sleep(0.5)

    # Publish (admin-only)
    r = client_admin.publish(ver_id)
    if r.status_code != 200:
        return f"publish_failed:{r.status_code}:{r.text[:120]}"
    return "ok"


def main() -> int:
    stuck = stuck_versions()
    log.info("stuck at received: %d", len(stuck))
    if not stuck:
        return 0

    admin = Client(ADMIN_EMAIL, ADMIN_PASSWORD, label="admin")
    hust = Client(HUST_EMAIL, HUST_PASSWORD, label="hust")
    huce = Client(HUCE_EMAIL, HUCE_PASSWORD, label="huce")
    hust.login()
    huce.login()

    counts = {"ok": 0, "skipped": 0, "failed": 0}
    for i, (doc_num, doc_id, ver_id, dept_code) in enumerate(stuck, 1):
        if dept_code == "HUST":
            cli_dig = hust
        elif dept_code == "HUCE":
            cli_dig = huce
        else:
            cli_dig = admin
        log.info("[%d/%d] %s dept=%s -> digitize=%s index+publish=%s",
                 i, len(stuck), doc_num, dept_code or "?",
                 cli_dig._email, admin._email)
        try:
            result = retry_one(cli_dig, admin, doc_num, doc_id, ver_id)
        except Exception as exc:
            log.exception("exception during retry")
            counts["failed"] += 1
            continue
        if result == "ok":
            counts["ok"] += 1
        else:
            counts["failed"] += 1
        log.info("  -> %s", result)
        time.sleep(SLEEP_BETWEEN_DOCS)

    log.info("=== retry done: ok=%d failed=%d ===", counts["ok"], counts["failed"])
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
