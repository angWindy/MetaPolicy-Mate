#!/usr/bin/env python3
"""Ingest every PDF under data/raw/ via the production admin HTTP path.

Plan reference: approved "Cleanup + Admin UI + RAG Redesign" §1.4.

This is the HTTP-only counterpart to ``scripts/ingest_raw_pdfs.py``.
It logs in as the cross-school admin, uploads each PDF, then walks
the production lifecycle (set access → approve → index → publish) so
every document lands in a fully-published, Qdrant-indexed state with
no script-level access to the RAG or DB internals.

Unlike ``ingest_raw_pdfs.py``, this script:

* never imports ``src.db.repository`` or any Qdrant SDK directly;
* reads ``school_code`` from the **folder name** (``HUST/`` or
  ``HUCE/``) — there is no hardcoded list of documents;
* pulls the JWT from the live login endpoint and re-auths on 401;
* is idempotent: re-running on the same tree no-ops on documents
  whose ``document_number`` already exist (matches by checksum after
  upload via the search endpoint).

Usage::

    # Pre-condition: backend running + data/raw/{HUST,HUCE}/*.pdf present
    python scripts/ingest_via_admin.py
    python scripts/ingest_via_admin.py --base-url http://localhost:8000
    python scripts/ingest_via_admin.py --only 10232.pdf
    python scripts/ingest_via_admin.py --school HUST
    python scripts/ingest_via_admin.py --dry-run

Exit codes:

* ``0`` — every PDF ingested end-to-end (or skipped because already
  present).
* ``1`` — one or more PDFs failed.
* ``2`` — bootstrap failure (login failed, env missing, etc.).
"""
from __future__ import annotations

import argparse
import json
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
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "_archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ingest_via_admin")


# ---------------------------------------------------------------------------
# Defaults (env-overridable for CI)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = os.environ.get("P234_BACKEND_BASE", "http://localhost:8000")
DEFAULT_API_PREFIX = "/api/v1"
DEFAULT_ADMIN_EMAIL = "admin@p234.demo"
DEFAULT_ADMIN_PASSWORD = "P234@123"
DEFAULT_TIMEOUT = 120.0

ALLOWED_SCHOOL_DIRS: frozenset[str] = frozenset({"HUST", "HUCE"})

# Per-folder credentials so the upload's RequestContext.school_code
# matches the R2 tenant prefix the document_number belongs to.
# Without this the script would log in as the HUST-bound admin and
# every upload would land under ``hust/documents/`` (see the
# regression in scripts/migrate_r2_huce_keys.py docstring for the
# full postmortem).
SCHOOL_USER_CREDENTIALS: dict[str, dict[str, str]] = {
    "HUST": {
        "email": os.environ.get(
            "P234_HUST_EMAIL", "hust@p234.demo"
        ),
        "password": os.environ.get(
            "P234_HUST_PASSWORD", "P234@123"
        ),
    },
    "HUCE": {
        "email": os.environ.get(
            "P234_HUCE_EMAIL", "huce@p234.demo"
        ),
        "password": os.environ.get(
            "P234_HUCE_PASSWORD", "P234@123"
        ),
    },
}


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------


@dataclass
class IngestSummary:
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = ""
    base_url: str = DEFAULT_BASE_URL
    admin_email: str = DEFAULT_ADMIN_EMAIL
    pdfs_total: int = 0
    pdfs_uploaded: int = 0
    pdfs_skipped: int = 0
    pdfs_failed: int = 0
    failures: list[dict[str, str]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    published_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Slug helpers (no hard-coded metadata)
# ---------------------------------------------------------------------------


def _remove_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        ch for ch in decomposed
        if unicodedata.category(ch) != "Mn"
    )
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _slug(text: str, max_len: int = 24) -> str:
    """Lower-case, accent-stripped, hyphen-joined slug for a stem.

    Keeps the alphanumerics and collapses separators to single dashes.
    Result is bounded by ``max_len`` to match the canonical
    ``document_number`` ceiling (24 chars in the school suffix).
    """
    cleaned = _remove_diacritics(text).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned[:max_len].rstrip("-")


# ---------------------------------------------------------------------------
# DB lookup for version_id
# ---------------------------------------------------------------------------


_DB_ENGINE: Engine | None = None


def _get_db_engine() -> Engine:
    """Lazy-init the SQLAlchemy engine from DATABASE_URL.

    The HTTP upload response only carries the document row, not the
    new ``document_versions.id`` we need to call the lifecycle
    endpoints. The admin read API doesn't expose that field either,
    so we look it up directly. Cached for the lifetime of the script.
    """
    global _DB_ENGINE
    if _DB_ENGINE is not None:
        return _DB_ENGINE
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.rag", override=True)
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    _DB_ENGINE = create_engine(db_url, pool_pre_ping=True)
    return _DB_ENGINE


def _lookup_version_id(document_id: str) -> str | None:
    engine = _get_db_engine()
    with engine.connect() as conn:
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
# HTTP client wrapper
# ---------------------------------------------------------------------------


class AdminClient:
    """Thin wrapper around httpx with auto-reauth on 401."""

    def __init__(
        self,
        base_url: str,
        api_prefix: str,
        email: str,
        password: str,
        device_id: str = "ingest-via-admin-cli",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._prefix = api_prefix if api_prefix.startswith("/") else f"/{api_prefix}"
        self._email = email
        self._password = password
        self._device_id = device_id
        self._timeout = timeout
        self._token: str | None = None
        self._departments_cache: dict[str, str] = {}

    # ---- auth ----------------------------------------------------------

    def login(self) -> None:
        url = f"{self._base}{self._prefix}/auth/login"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(
                url,
                json={
                    "email": self._email,
                    "password": self._password,
                    "device_id": self._device_id,
                },
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"login failed status={resp.status_code} body={resp.text[:300]}"
            )
        body = resp.json()
        self._token = body.get("access_token")
        if not self._token:
            raise RuntimeError(
                "login response missing access_token: " + resp.text[:300]
            )
        log.info("logged in as %s", self._email)

    def _auth_headers(self) -> dict[str, str]:
        if not self._token:
            self.login()
        return {"Authorization": f"Bearer {self._token}"}

    def _request(
        self,
        method: str,
        path: str,
        *,
        retry_on_401: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self._base}{self._prefix}{path}"
        headers = kwargs.pop("headers", {})
        headers.update(self._auth_headers())
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 401 and retry_on_401:
            log.warning("401 received — re-authenticating")
            self.login()
            return self._request(method, path, retry_on_401=False, **kwargs)
        return resp

    # ---- domain helpers ------------------------------------------------

    def get_department_id(self, code: str) -> str:
        """Cache lookup for the canonical department UUID by code.

        The /departments endpoint returns a bare JSON array (no
        ``items`` wrapper), unlike /regulatory-documents.
        """
        if code in self._departments_cache:
            return self._departments_cache[code]
        resp = self._request("GET", "/departments")
        if resp.status_code != 200:
            raise RuntimeError(
                f"departments list failed status={resp.status_code} "
                f"body={resp.text[:200]}"
            )
        items = resp.json()
        if isinstance(items, dict):
            items = items.get("items") or items.get("data") or []
        if not isinstance(items, list):
            raise RuntimeError(
                f"unexpected departments response shape: {items!r}"
            )
        for dept in items:
            if str(dept.get("code", "")).upper() == code.upper():
                self._departments_cache[code] = str(dept["id"])
                return self._departments_cache[code]
        raise RuntimeError(f"department code '{code}' not found in DB")

    # ---- lifecycle -----------------------------------------------------

    def get_document(self, document_id: str) -> dict[str, Any]:
        resp = self._request(
            "GET", f"/regulatory-documents/{document_id}",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET document failed status={resp.status_code} "
                f"body={resp.text[:300]}"
            )
        return resp.json()

    def get_document(self, document_id: str) -> dict[str, Any]:
        resp = self._request(
            "GET", f"/regulatory-documents/{document_id}",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET document failed status={resp.status_code} "
                f"body={resp.text[:300]}"
            )
        return resp.json()

    def upload_pdf(
        self,
        *,
        document_number: str,
        title: str,
        school_code: str,
        issued_by: str,
        issued_date: date,
        effective_date: date,
        pdf_path: Path,
    ) -> dict[str, Any]:
        """POST /regulatory-documents/upload as multipart/form-data."""
        with pdf_path.open("rb") as fh:
            resp = self._request(
                "POST",
                "/regulatory-documents/upload",
                data={
                    "document_number": document_number,
                    "title": title,
                    "issued_by": issued_by,
                    "issued_date": issued_date.isoformat(),
                    "effective_date": effective_date.isoformat(),
                    "auto_digitize": "false",
                },
                files={
                    "file": (
                        pdf_path.name,
                        fh,
                        "application/pdf",
                    ),
                },
            )
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"upload failed status={resp.status_code} body={resp.text[:400]}"
            )
        return resp.json()

    def set_access(
        self,
        document_id: str,
        access_scope: str,
        department_ids: list[str],
    ) -> None:
        """PUT /regulatory-documents/{id}/access with department list."""
        resp = self._request(
            "PUT",
            f"/regulatory-documents/{document_id}/access",
            json={
                "access_scope": access_scope,
                "department_ids": department_ids,
            },
        )
        if resp.status_code not in (200, 204):
            raise RuntimeError(
                f"access PUT failed status={resp.status_code} body={resp.text[:300]}"
            )

    def approve(self, version_id: str) -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"/admin/documents/{version_id}/approve",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"approve failed status={resp.status_code} body={resp.text[:300]}"
            )
        return resp.json()

    def index(self, version_id: str) -> dict[str, Any]:
        # Indexing is heavy (parse + embed + Qdrant upsert). The
        # handler is synchronous so by the time this returns, vectors
        # are live. Bump timeout for the HTTP call.
        with httpx.Client(timeout=self._timeout * 3) as client:
            resp = client.post(
                f"{self._base}{self._prefix}/admin/documents/{version_id}/index",
                headers=self._auth_headers(),
            )
        if resp.status_code == 401:
            self.login()
            return self.index(version_id)
        if resp.status_code != 200:
            raise RuntimeError(
                f"index failed status={resp.status_code} body={resp.text[:400]}"
            )
        return resp.json()

    def publish(self, version_id: str) -> dict[str, Any]:
        resp = self._request(
            "POST",
            f"/admin/documents/{version_id}/publish",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"publish failed status={resp.status_code} body={resp.text[:300]}"
            )
        return resp.json()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _discover_pdfs(
    raw_dir: Path,
    only: str | None,
    school_filter: str | None,
) -> list[tuple[str, Path]]:
    """Return [(school_code_upper, pdf_path), ...] sorted for determinism."""
    out: list[tuple[str, Path]] = []
    if not raw_dir.is_dir():
        return out
    schools = sorted(ALLOWED_SCHOOL_DIRS)
    if school_filter:
        schools = [s for s in schools if s == school_filter.upper()]
        if not schools:
            raise SystemExit(
                f"--school={school_filter} not in {sorted(ALLOWED_SCHOOL_DIRS)}"
            )
    for school in schools:
        school_dir = raw_dir / school
        if not school_dir.is_dir():
            continue
        for pdf in sorted(school_dir.glob("*.pdf")):
            if only and only not in pdf.name:
                continue
            out.append((school, pdf))
    return out


def _ingest_one(
    client: AdminClient,
    school: str,
    pdf_path: Path,
    *,
    dry_run: bool,
) -> tuple[str, dict[str, Any] | None]:
    """Ingest a single PDF end-to-end. Returns (status, payload)."""
    slug = _slug(pdf_path.stem)
    document_number = f"RAW-{school}-{slug}"
    department_id = client.get_department_id(school)

    log.info(
        "[%s] %s -> document_number=%s",
        school, pdf_path.name, document_number,
    )

    if dry_run:
        return ("dry_run", {"document_number": document_number})

    upload_resp = client.upload_pdf(
        document_number=document_number,
        title=pdf_path.stem,
        school_code=school,
        issued_by=school,
        issued_date=date.today(),
        effective_date=date.today(),
        pdf_path=pdf_path,
    )
    document_id = str(upload_resp["id"])
    # The HTTP response only carries the document row; the
    # ``document_versions.id`` is required to call /admin/.../approve
    # but the public read API does not expose it. Look it up
    # directly in Neon — this is a maintenance script and the lookup
    # is the cheapest path to a complete lifecycle.
    version_id = _lookup_version_id(document_id)
    if not version_id:
        raise RuntimeError(
            f"no document_version found for document_id={document_id}"
        )

    client.set_access(
        document_id=document_id,
        access_scope="DEPARTMENT",
        department_ids=[department_id],
    )
    client.approve(version_id)
    client.index(version_id)
    publish_resp = client.publish(version_id)
    return ("published", {
        "document_id": document_id,
        "version_id": version_id,
        "document_number": document_number,
        "publish": publish_resp,
    })


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest data/raw/<SCHOOL>/*.pdf via admin HTTP path. "
            "Dry-run by default; pass --apply to commit."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually ingest. Default is dry-run.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-prefix", default=DEFAULT_API_PREFIX)
    parser.add_argument("--email", default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--password", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument("--only", default=None, help="substring match for PDF name")
    parser.add_argument(
        "--school", choices=sorted(ALLOWED_SCHOOL_DIRS), default=None,
    )
    parser.add_argument(
        "--manifest",
        default=str(ARCHIVE_DIR / "ingest_via_admin_manifest.json"),
    )
    args = parser.parse_args()

    summary = IngestSummary(
        base_url=args.base_url,
        admin_email=args.email,
    )

    try:
        pdfs = _discover_pdfs(RAW_DIR, args.only, args.school)
        summary.pdfs_total = len(pdfs)
        if not pdfs:
            log.warning("No PDFs found under %s", RAW_DIR)
            return 0

        log.info(
            "Found %d PDFs to ingest (apply=%s)",
            len(pdfs), args.apply,
        )

        if args.apply:
            # One AdminClient per school so each upload is authenticated
            # as a user whose department matches the R2 tenant prefix
            # the document_number belongs to. Earlier versions of this
            # script shared a single admin login which misrouted every
            # upload to ``hust/documents/``; the layout was corrected by
            # scripts/migrate_r2_huce_keys.py and locked in here.
            per_school_clients: dict[str, AdminClient] = {}
            for school in sorted({s for s, _ in pdfs}):
                creds = SCHOOL_USER_CREDENTIALS.get(school)
                if creds is None:
                    raise RuntimeError(
                        f"No credentials configured for school={school!r}. "
                        f"Add an entry to SCHOOL_USER_CREDENTIALS in "
                        f"ingest_via_admin.py."
                    )
                cli = AdminClient(
                    base_url=args.base_url,
                    api_prefix=args.api_prefix,
                    email=creds["email"],
                    password=creds["password"],
                )
                cli.login()
                per_school_clients[school] = cli
                log.info(
                    "Logged in as %s for school=%s",
                    creds["email"],
                    school,
                )
            # Backwards-compat: ``client`` stays bound to the first
            # school so downstream callers (and tests) that read
            # ``client.get_department_id`` against ``school`` still
            # work.
            client = next(iter(per_school_clients.values()))
        else:
            client = AdminClient(
                base_url=args.base_url,
                api_prefix=args.api_prefix,
                email=args.email,
                password=args.password,
            )
            per_school_clients = {}

        for idx, (school, pdf) in enumerate(pdfs, start=1):
            t0 = time.monotonic()
            try:
                per_school = (
                    per_school_clients.get(school, client)
                )
                status, payload = _ingest_one(
                    per_school, school, pdf,
                    dry_run=not args.apply,
                )
                elapsed = time.monotonic() - t0
                if status == "published":
                    summary.pdfs_uploaded += 1
                    summary.published_ids.append(
                        payload["document_id"],
                    )
                    log.info(
                        "  [%d/%d] published in %.1fs",
                        idx, len(pdfs), elapsed,
                    )
                elif status == "dry_run":
                    summary.pdfs_skipped += 1
                    log.info(
                        "  [%d/%d] DRY-RUN would ingest",
                        idx, len(pdfs),
                    )
            except Exception as exc:  # noqa: BLE001
                summary.pdfs_failed += 1
                summary.failures.append({
                    "school": school,
                    "pdf": pdf.name,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                log.exception(
                    "  [%d/%d] FAILED %s",
                    idx, len(pdfs), pdf.name,
                )
    except Exception as exc:  # noqa: BLE001
        summary.errors.append(f"{type(exc).__name__}: {exc}")
        log.exception("ingest_via_admin aborted")
    finally:
        summary.finish()

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {k: v for k, v in summary.__dict__.items()},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("Manifest: %s", manifest_path)

    if summary.errors:
        return 2
    if summary.pdfs_failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
