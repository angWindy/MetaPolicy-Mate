#!/usr/bin/env python3
"""Move R2 source.pdf files for PUBLIC documents under the ``public/`` prefix.

Plan: approved "Permission Sync & R2 Folder".

Context
--------
PUBLIC documents were historically uploaded under the uploader's school
tenant prefix (``hust/documents/...``, ``huce/documents/...``) because
``ObjectKeyBuilder.for_version`` only accepted a ``tenant_code``. Now
that the builder takes an ``access_scope`` argument, PUBLIC documents
should always land under the canonical ``public/documents/...`` folder
so anyone can resolve them by that single prefix.

This script:

1. Lists every document with ``access_scope = 'PUBLIC'``.
2. For each, computes the canonical key with ``access_scope='PUBLIC'``.
3. If the current DB ``object_key`` already matches the canonical key
   → skip (idempotent).
4. If the canonical key does NOT exist yet in R2 but the source
   ``object_key`` does → ``copy_object`` server-side, then update the
   DB row's ``object_key`` to the canonical key. The old key is
   recorded in ``migration_manifest.json`` so the orphan-sweep can
   clean it up after a verification window.
5. If neither exists → mark as ``missing_source``; no copy, no DB
   change.

The script defaults to ``--dry-run``: it prints the plan and writes
``migration_manifest.json`` without mutating R2 or DB. Pass ``--apply``
to commit.

Usage::

    python scripts/migrate_r2_public_folder.py
    python scripts/migrate_r2_public_folder.py --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from src.config import get_settings  # noqa: E402
from scripts._r2_maintenance import (  # noqa: E402
    R2Maintenance,
)
from src.infrastructure.storage.object_key import (  # noqa: E402
    ObjectKeyBuilder,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate_r2_public_folder")


def _to_psycopg_url(db_url: str) -> str:
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


def _load_public_documents(
    engine: Any,
) -> list[dict[str, Any]]:
    """Return every PUBLIC document + its current object_key.

    Joins ``documents`` → ``document_versions`` to pick the latest
    version's ``object_key`` per document (the version that was last
    reindexed is the one carrying the active Qdrant chunks).
    """
    sql = text(
        """
        SELECT
            d.id            AS document_id,
            d.document_number,
            v.id            AS version_id,
            v.version_number,
            v.object_key
        FROM documents d
        JOIN document_versions v
            ON v.document_id = d.id
        WHERE d.access_scope = 'PUBLIC'
          AND v.version_number = (
              SELECT MAX(v2.version_number)
              FROM document_versions v2
              WHERE v2.document_id = d.id
          )
        ORDER BY d.document_number
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql).mappings().all()
    return [dict(row) for row in rows]


def _expected_public_key(
    builder: ObjectKeyBuilder,
    document_number: str,
    version_number: int,
) -> str:
    """The canonical PUBLIC key for the given document/version."""
    return builder.for_version(
        document_number=document_number,
        version_number=version_number,
        tenant_code=None,
        access_scope="PUBLIC",
    )


def _manifest_path(
    output_dir: Path,
) -> Path:
    return output_dir / "public_folder_migration_manifest.json"


def run(
    *,
    apply: bool,
    output_dir: Path,
) -> int:
    settings = get_settings()
    builder = ObjectKeyBuilder(settings)
    r2 = R2Maintenance(
        endpoint=settings.r2_endpoint,
        access_key_id=(
            settings.r2_access_key_id
        ),
        secret_access_key=(
            settings.r2_secret_access_key
        ),
        bucket_name=(
            settings.r2_bucket_name
        ),
    )

    engine = create_engine(
        _to_psycopg_url(settings.database_url),
        future=True,
    )

    docs = _load_public_documents(engine)
    log.info(
        "found %d PUBLIC documents to inspect",
        len(docs),
    )

    manifest: list[dict[str, Any]] = []
    counters = {
        "already_canonical": 0,
        "copied": 0,
        "missing_source": 0,
        "missing_canonical": 0,
    }

    for doc in docs:
        document_id = str(
            doc["document_id"]
        )
        document_number = (
            doc["document_number"]
        )
        version_number = int(
            doc["version_number"]
        )
        current_key = doc["object_key"]
        canonical_key = _expected_public_key(
            builder,
            document_number,
            version_number,
        )

        record: dict[str, Any] = {
            "document_id": document_id,
            "document_number": (
                document_number
            ),
            "version_number": (
                version_number
            ),
            "current_object_key": (
                current_key
            ),
            "canonical_object_key": (
                canonical_key
            ),
        }

        if current_key == canonical_key:
            record["action"] = (
                "already_canonical"
            )
            counters["already_canonical"] += 1
            manifest.append(record)
            continue

        canonical_head = r2.head_object(
            canonical_key
        )
        current_head = r2.head_object(
            current_key
        )

        if canonical_head is not None:
            record["action"] = (
                "canonical_present_already"
            )
            record["note"] = (
                "canonical key already exists; "
                "leaving the legacy key for the "
                "sweep script"
            )
            counters["already_canonical"] += 1
            manifest.append(record)
            continue

        if current_head is None:
            record["action"] = (
                "missing_source"
            )
            record["note"] = (
                "neither current nor canonical key "
                "found in R2; nothing to migrate"
            )
            counters["missing_source"] += 1
            manifest.append(record)
            continue

        if apply:
            r2.copy_object(
                source_key=current_key,
                dest_key=(
                    canonical_key
                ),
            )
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE document_versions "
                        "SET object_key = :new_key "
                        "WHERE id = :version_id"
                    ),
                    {
                        "new_key": (
                            canonical_key
                        ),
                        "version_id": (
                            doc["version_id"]
                        ),
                    },
                )
            record["action"] = (
                "copied_and_db_updated"
            )
            counters["copied"] += 1
        else:
            record["action"] = (
                "would_copy_and_update_db"
            )
            counters["missing_canonical"] += 1

        manifest.append(record)

    output_dir.mkdir(
        parents=True, exist_ok=True
    )
    manifest_path = _manifest_path(output_dir)
    manifest_path.write_text(
        json.dumps(
            {
                "counters": counters,
                "items": manifest,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info(
        "wrote manifest to %s", manifest_path
    )
    log.info("counters: %s", counters)
    if not apply:
        log.warning(
            "dry-run only; pass --apply to commit"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Move R2 source.pdf files for PUBLIC "
            "documents to the public/ prefix"
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually copy in R2 and update the DB. "
            "Default is dry-run."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/p234-r2-migration"),
        help=(
            "Where to drop "
            "public_folder_migration_manifest.json"
        ),
    )
    args = parser.parse_args()
    return run(
        apply=args.apply,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())