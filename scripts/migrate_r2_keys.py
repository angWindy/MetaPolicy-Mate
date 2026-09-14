#!/usr/bin/env python3
"""Migrate legacy R2 object keys to the canonical layout.

Plan: approved "Reorganize R2 + Comprehensive E2E" §1.3.

For every row in ``public.document_versions`` we compute the new
canonical key (``{tenant}/documents/{number}/v{n}/source.pdf``) via
``ObjectKeyBuilder`` and:

* If the new key already exists in R2 → skip (idempotent re-run).
* If the old (DB) key exists in R2 and the new key does not →
  ``copy_object`` old→new server-side, then update the DB row's
  ``object_key`` to the new key. The old key is recorded in
  ``migration_manifest.json`` so the orphan-sweep script can clean it
  up after a verification window.
* If neither exists → mark as ``missing_source``; no copy, no DB
  change.

The migration is **forward-only**: it never deletes the old key. The
sweep script (``scripts/sweep_r2_orphans.py``) is responsible for
cleanup, after a human has eyeballed the manifest.

The script defaults to ``--dry-run``: it prints the plan and writes
``migration_manifest.json`` (without mutating R2 or DB). Pass
``--apply`` to commit.

Usage::

    python scripts/migrate_r2_keys.py
    python scripts/migrate_r2_keys.py --apply
    python scripts/migrate_r2_keys.py --tenant=hust
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
log = logging.getLogger("migrate_r2_keys")


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


def _query_versions(
    engine: Any,
    tenant_code: str | None,
) -> list[dict[str, Any]]:
    """Return one row per version with the joined document number."""
    params: dict[str, Any] = {}
    filter_sql = ""
    if tenant_code:
        filter_sql = (
            " WHERE LOWER(d.document_number) LIKE :prefix"
        )
        params["prefix"] = f"{tenant_code.lower()}%"

    sql = text(
        f"""
        SELECT
          v.id AS version_id,
          v.document_id,
          v.version_number,
          v.object_key AS old_key,
          d.document_number
        FROM public.document_versions v
        JOIN public.documents d
          ON d.id = v.document_id
        {filter_sql}
        ORDER BY d.document_number ASC, v.version_number ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


def _update_object_key(
    engine: Any,
    version_id: str,
    new_key: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE public.document_versions "
                "SET object_key = :new_key "
                "WHERE id = :version_id"
            ),
            {"new_key": new_key, "version_id": version_id},
        )


def _persist_manifest(
    manifest_path: Path,
    payload: dict[str, Any],
) -> None:
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate legacy R2 keys to the canonical layout."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Commit R2 copies + DB updates. "
            "Default is dry-run (manifest only)."
        ),
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help=(
            "Restrict to documents whose number starts with "
            "this tenant code (e.g. 'hust'). Default: all."
        ),
    )
    parser.add_argument(
        "--manifest",
        default="migration_manifest.json",
        help="Path to the migration manifest JSON.",
    )
    args = parser.parse_args()

    settings = get_settings()
    builder = ObjectKeyBuilder(settings)
    r2 = R2Maintenance(
        endpoint=settings.r2_endpoint,
        access_key_id=settings.r2_access_key_id,
        secret_access_key=(
            settings.r2_secret_access_key
        ),
        bucket_name=settings.r2_bucket_name,
    )
    engine = create_engine(
        _to_psycopg_url(settings.database_url)
    )

    rows = _query_versions(engine, args.tenant)
    log.info(
        "Discovered %d document_versions rows to inspect",
        len(rows),
    )

    plan: list[dict[str, Any]] = []
    skipped_already_canonical = 0
    skipped_missing_source = 0
    to_copy = 0
    copied = 0
    errors: list[str] = []

    for row in rows:
        version_id = str(row["version_id"])
        old_key = row["old_key"]
        document_number = row["document_number"]
        version_number = int(row["version_number"])

        new_key = builder.for_version(
            document_number=document_number,
            version_number=version_number,
        )

        if new_key == old_key:
            skipped_already_canonical += 1
            continue

        # Probe both keys.
        try:
            new_exists = r2.head_object(new_key) is not None
            old_exists = r2.head_object(old_key) is not None
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"head_object failed on version_id={version_id}: {exc}"
            )
            continue

        if new_exists and not old_exists:
            # Already migrated by a previous run; the DB just hasn't
            # caught up yet.
            plan.append(
                {
                    "version_id": version_id,
                    "old_key": old_key,
                    "new_key": new_key,
                    "action": "update_db_only",
                    "reason": "new_key_present_in_r2_old_missing",
                }
            )
            if args.apply:
                try:
                    _update_object_key(
                        engine,
                        version_id,
                        new_key,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        f"db_update failed on "
                        f"version_id={version_id}: {exc}"
                    )
            continue

        if new_exists and old_exists:
            # Both exist. DB still points at old. Treat as DB-only
            # update; sweep will deal with the old key once we
            # confirm the new one is reachable.
            plan.append(
                {
                    "version_id": version_id,
                    "old_key": old_key,
                    "new_key": new_key,
                    "action": "update_db_only",
                    "reason": "new_and_old_both_present",
                }
            )
            if args.apply:
                try:
                    _update_object_key(
                        engine,
                        version_id,
                        new_key,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        f"db_update failed on "
                        f"version_id={version_id}: {exc}"
                    )
            continue

        if (not new_exists) and old_exists:
            to_copy += 1
            plan.append(
                {
                    "version_id": version_id,
                    "old_key": old_key,
                    "new_key": new_key,
                    "action": "copy_then_update",
                    "reason": "old_present_new_missing",
                }
            )
            if args.apply:
                try:
                    r2.copy_object(old_key, new_key)
                    _update_object_key(
                        engine,
                        version_id,
                        new_key,
                    )
                    copied += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        f"copy/update failed on "
                        f"version_id={version_id}: {exc}"
                    )
            continue

        # Neither present.
        skipped_missing_source += 1
        plan.append(
            {
                "version_id": version_id,
                "old_key": old_key,
                "new_key": new_key,
                "action": "skip",
                "reason": "source_pdf_missing_everywhere",
            }
        )

    manifest = {
        "tenant_filter": args.tenant,
        "apply": args.apply,
        "totals": {
            "rows_inspected": len(rows),
            "already_canonical": (
                skipped_already_canonical
            ),
            "to_copy": to_copy,
            "copied": copied,
            "missing_source": skipped_missing_source,
            "errors": len(errors),
        },
        "plan": plan,
        "errors": errors,
    }

    manifest_path = Path(args.manifest)
    _persist_manifest(manifest_path, manifest)

    print(json.dumps(manifest["totals"], indent=2))
    print(f"Manifest written to: {manifest_path}")
    if errors:
        print(
            f"  ERRORS: {len(errors)} "
            "(see manifest.errors for details)"
        )
    if not args.apply:
        print(
            "Dry-run only. Re-run with --apply to commit "
            "R2 copies + DB updates."
        )
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())