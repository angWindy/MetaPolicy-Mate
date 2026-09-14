#!/usr/bin/env python3
"""Seed regulatory documents from data/raw/ PDFs into Postgres + R2.

This is the Phase-4 bootstrap script for the P-234 demo. For every PDF
under ``data/raw/`` it:

  * Uploads the bytes to Cloudflare R2 (bucket ``p234-storage``).
  * Creates a row in ``public.documents`` and a matching
    ``public.document_versions`` row at ``legal_status=draft``,
    ``processing_status=received``.
  * Picks ``access_scope=department`` for HUCE/HUST datasets, otherwise
    ``public``.

The script is idempotent: existing documents are detected by
``document_number`` and skipped (with a clear ``SKIP`` line in the
output).

Required services (Docker-first):

* Postgres (Neon) — reachable via ``DATABASE_URL``.
* Cloudflare R2 — reachable via ``R2_ENDPOINT`` /
  ``R2_ACCESS_KEY_ID`` / ``R2_SECRET_ACCESS_KEY`` / ``R2_BUCKET_NAME``.

Usage::

    python scripts/seed_pdfs.py
    python scripts/seed_pdfs.py --only 10232.pdf
    python scripts/seed_pdfs.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import sys
from pathlib import Path
from uuid import UUID, uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.infrastructure.storage.object_key import (  # noqa: E402
    ObjectKeyBuilder,
)
from src.infrastructure.storage.r2_file_storage import (  # noqa: E402
    R2FileStorage,
)
from src.domain.enums.document_access_scope import (  # noqa: E402
    DocumentAccessScope,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("seed_pdfs")


RAW_DIR = PROJECT_ROOT / "data" / "raw"


def list_pdfs(only: str | None) -> list[Path]:
    pdfs: list[Path] = []
    if not RAW_DIR.is_dir():
        return pdfs
    for path in sorted(RAW_DIR.rglob("*.pdf")):
        if only and only not in path.name:
            continue
        pdfs.append(path)
    return pdfs


def _to_psycopg_url(db_url: str) -> str:
    """Normalise a DATABASE_URL so SQLAlchemy uses psycopg v3."""
    if db_url.startswith("postgresql+psycopg://"):
        return db_url
    if db_url.startswith("postgresql+psycopg2://"):
        return db_url.replace(
            "postgresql+psycopg2://",
            "postgresql+psycopg://",
            1,
        )
    if db_url.startswith("postgresql://"):
        return db_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )
    return db_url


def _make_engine() -> Engine:
    settings = get_settings()
    return create_engine(_to_psycopg_url(settings.database_url))


def _infer_school(pdf_path: Path) -> str:
    """Infer school from immediate parent directory name.
    
    Only HUST/ and HUCE/ top-level folders are allowed.
    Any subdirectory (like RAW-HUST-xxx) is not permitted.
    """
    parts = pdf_path.parts
    # Find the position of 'raw' in the path
    try:
        raw_idx = parts.index("raw")
    except ValueError:
        return "CROSS"
    
    # The school folder should be directly under 'raw'
    if len(parts) > raw_idx + 1:
        school_folder = parts[raw_idx + 1].upper()
        if school_folder == "HUST":
            return "HUST"
        if school_folder == "HUCE":
            return "HUCE"
    
    return "CROSS"


def _slugify(s: str, max_len: int = 64) -> str:
    safe: list[str] = []
    for ch in s:
        if ch.isalnum() or ch in "-_":
            safe.append(ch)
        elif ch in (" ", "."):
            safe.append("-")
    out = "".join(safe).strip("-")
    return out[:max_len] or "doc"


def _build_r2_storage() -> R2FileStorage:
    settings = get_settings()
    return R2FileStorage(
        endpoint=settings.r2_endpoint,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=(
            settings.r2_secret_access_key
        ),
        bucket_name=settings.r2_bucket_name,
    )


def document_exists(
    engine: Engine,
    document_number: str,
) -> bool:
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT 1 FROM public.documents "
                "WHERE document_number = :n "
                "LIMIT 1"
            ),
            {"n": document_number},
        ).first()
        return result is not None


async def seed_one(
    engine: Engine,
    storage: R2FileStorage | None,
    pdf_path: Path,
    *,
    dry_run: bool,
) -> str:
    raw_bytes = pdf_path.read_bytes()
    if not raw_bytes:
        return "SKIP empty"

    school = _infer_school(pdf_path)
    slug = _slugify(pdf_path.stem)
    document_number = f"SEED-{school}-{slug}"[:120]

    if document_exists(engine, document_number):
        return "SKIP exists"

    checksum = hashlib.sha256(
        raw_bytes,
    ).hexdigest()

    document_id = uuid4()
    version_id = uuid4()
    # Use the canonical ObjectKeyBuilder so the seed key matches the
    # production upload/replace-source handlers' layout (single source
    # of truth). Tenant defaults to lowercase school code; for CROSS
    # we fall back to ``hust`` since the bucket is currently
    # single-tenant.
    tenant_for_seed = (
        school.lower()
        if school in {"HUST", "HUCE"}
        else "hust"
    )
    object_key = ObjectKeyBuilder(
        get_settings()
    ).for_version(
        document_number=document_number,
        version_number=1,
        tenant_code=tenant_for_seed,
    )

    if dry_run or storage is None:
        return (
            f"DRY would insert "
            f"{document_number} "
            f"({len(raw_bytes)} bytes)"
        )

    # Upload to R2 first so a DB-only insert doesn't dangle.
    await storage.upload(
        object_key=object_key,
        content=raw_bytes,
        content_type="application/pdf",
    )

    issued_date = "2026-01-01"
    effective_date = "2026-01-01"

    with engine.begin() as conn:
        # Ensure HUST/HUCE departments exist so we can satisfy the
        # department FK on document_departments.
        hust_dept = conn.execute(
            text(
                "SELECT id FROM public.departments "
                "WHERE code = 'HUST' LIMIT 1"
            ),
        ).first()
        huce_dept = conn.execute(
            text(
                "SELECT id FROM public.departments "
                "WHERE code = 'HUCE' LIMIT 1"
            ),
        ).first()

        department_id: UUID | None = None
        if school == "HUST" and hust_dept:
            department_id = hust_dept[0]
        elif school == "HUCE" and huce_dept:
            department_id = huce_dept[0]

        access_scope = (
            DocumentAccessScope.DEPARTMENT.value
            if department_id is not None
            else DocumentAccessScope.PUBLIC.value
        )

        conn.execute(
            text(
                "INSERT INTO public.documents ("
                "  id, document_number, title, "
                "  issued_by, issued_date, "
                "  effective_date, "
                "  legal_status, "
                "  access_scope, "
                "  created_at, updated_at"
                ") VALUES ("
                "  :id, :num, :title, "
                "  :issued_by, :issued_date, "
                "  :effective_date, "
                "  :legal_status, "
                "  :access_scope, "
                "  NOW(), NULL"
                ")"
            ),
            {
                "id": str(document_id),
                "num": document_number,
                "title": pdf_path.stem[:200],
                "issued_by": school,
                "issued_date": issued_date,
                "effective_date": effective_date,
                "legal_status": "draft",
                "access_scope": access_scope,
            },
        )

        conn.execute(
            text(
                "INSERT INTO public.document_versions ("
                "  id, document_id, version_number, "
                "  processing_status, checksum, "
                "  source_filename, object_key, "
                "  content_type, size_bytes, "
                "  replaces_version_id, "
                "  created_at"
                ") VALUES ("
                "  :id, :doc_id, 1, "
                "  :processing_status, "
                "  :checksum, "
                "  :source_filename, "
                "  :object_key, "
                "  :content_type, "
                "  :size_bytes, "
                "  NULL, NOW()"
                ")"
            ),
            {
                "id": str(version_id),
                "doc_id": str(document_id),
                "processing_status": "received",
                "checksum": checksum,
                "source_filename": pdf_path.name,
                "object_key": object_key,
                "content_type": "application/pdf",
                "size_bytes": len(raw_bytes),
            },
        )

        if department_id is not None:
            conn.execute(
                text(
                    "INSERT INTO public.document_departments ("
                    "  document_id, department_id"
                    ") VALUES ("
                    "  :doc_id, :dept_id"
                    ") ON CONFLICT DO NOTHING"
                ),
                {
                    "doc_id": str(document_id),
                    "dept_id": str(department_id),
                },
            )

    return (
        f"INSERTED "
        f"({access_scope}, "
        f"{len(raw_bytes)} bytes) "
        f"-> {object_key}"
    )


async def main_async(args: argparse.Namespace) -> int:
    pdfs = list_pdfs(args.only)
    if args.limit:
        pdfs = pdfs[: args.limit]

    if not pdfs:
        log.warning("No PDFs matched under %s", RAW_DIR)
        return 0

    log.info(
        "Found %d PDFs under %s",
        len(pdfs),
        RAW_DIR,
    )

    engine = _make_engine()
    storage: R2FileStorage | None = None
    if not args.dry_run:
        storage = _build_r2_storage()

    inserted = 0
    skipped = 0
    failed = 0
    for idx, pdf in enumerate(pdfs, start=1):
        try:
            result = await seed_one(
                engine,
                storage,
                pdf,
                dry_run=args.dry_run,
            )
            log.info(
                "[%d/%d] %s :: %s",
                idx,
                len(pdfs),
                pdf.name,
                result,
            )
            if result.startswith("INSERTED"):
                inserted += 1
            elif result.startswith("SKIP"):
                skipped += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.exception(
                "[%d/%d] FAILED %s: %s",
                idx,
                len(pdfs),
                pdf.name,
                exc,
            )

    log.info(
        "Done. total=%d inserted=%d skipped=%d failed=%d",
        len(pdfs),
        inserted,
        skipped,
        failed,
    )
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Seed regulatory documents from "
            "data/raw/ PDFs into Postgres + R2."
        ),
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Substring to match against PDF filename.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip R2/Postgres writes; report only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit how many PDFs to process (0 = no limit).",
    )
    args = parser.parse_args()

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())