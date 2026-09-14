#!/usr/bin/env python3
"""One-off + recovery utility: sync R2 object keys to current access_scope.

Recomputes the canonical key for every ``document_versions`` row using
``ObjectKeyBuilder.for_version(..., access_scope=document.access_scope)``
and copies the R2 object when the canonical key differs from the stored
key. Updates ``document_versions.object_key`` to match.

This script is **forward-only** like ``scripts/migrate_r2_keys.py``:
it never deletes the old key. Operators run
``scripts/sweep_r2_orphans.py --apply`` afterwards to clean up.

Default is dry-run (manifest only). Pass ``--apply`` to commit.

Usage::

    python scripts/sync_r2_for_access_change.py            # dry-run
    python scripts/sync_r2_for_access_change.py --apply    # commit
    python scripts/sync_r2_for_access_change.py --document-id=<uuid>  # scoped
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
from scripts._r2_maintenance import R2Maintenance  # noqa: E402
from src.infrastructure.storage.object_key import (  # noqa: E402
    ObjectKeyBuilder,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sync_r2_for_access_change")


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


def _resolve_tenant_code(
    *,
    access_scope: str,
    department_codes: list[str],
) -> str | None:
    """Replicates the upload handler's tenant resolution for the new key."""
    if access_scope == "PUBLIC":
        return None
    if not department_codes:
        raise ValueError(
            "DEPARTMENT scope document has no bound departments; "
            "cannot compute canonical key."
        )
    return department_codes[0]


def _query_versions(
    engine: Any,
    document_id: str | None,
) -> list[dict[str, Any]]:
    """Return one row per version with the joined document + departments."""
    params: dict[str, Any] = {}
    filter_sql = ""
    if document_id:
        filter_sql = " WHERE v.document_id = :doc_id"
        params["doc_id"] = document_id

    sql = text(
        f"""
        SELECT
          v.id AS version_id,
          v.document_id,
          v.version_number,
          v.object_key AS old_key,
          d.document_number,
          d.access_scope,
          COALESCE(
            (
              SELECT string_agg(dep.code, ',' ORDER BY dep.code)
              FROM public.document_departments dd
              JOIN public.departments dep ON dep.id = dd.department_id
              WHERE dd.document_id = d.id AND dep.is_active = TRUE
            ),
            ''
          ) AS department_codes
        FROM public.document_versions v
        JOIN public.documents d ON d.id = v.document_id
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync R2 object keys to current access_scope."
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
        "--document-id",
        default=None,
        help=(
            "Restrict to a single document_id. "
            "Default: all documents."
        ),
    )
    parser.add_argument(
        "--manifest",
        default="sync_r2_manifest.json",
        help="Path to the sync manifest JSON.",
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

    rows = _query_versions(engine, args.document_id)
    log.info(
        "Discovered %d document_versions rows to inspect",
        len(rows),
    )

    plan: list[dict[str, Any]] = []
    skipped_aligned = 0
    skipped_missing_source = 0
    to_copy = 0
    copied = 0
    errors: list[str] = []

    for row in rows:
        version_id = str(row["version_id"])
        old_key = row["old_key"]
        document_number = row["document_number"]
        version_number = int(row["version_number"])
        access_scope = row["access_scope"]
        department_codes = [
            c.strip()
            for c in (row["department_codes"] or "").split(",")
            if c.strip()
        ]

        try:
            tenant_code = _resolve_tenant_code(
                access_scope=access_scope,
                department_codes=department_codes,
            )
        except ValueError as exc:
            errors.append(
                f"key resolution failed on version_id={version_id}: {exc}"
            )
            continue

        new_key = builder.for_version(
            document_number=document_number,
            version_number=version_number,
            tenant_code=tenant_code,
            access_scope=access_scope,
        )

        if new_key == old_key:
            skipped_aligned += 1
            continue

        try:
            old_exists = r2.head_object(old_key) is not None
            new_exists_before = r2.head_object(new_key) is not None
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"head_object failed on version_id={version_id}: {exc}"
            )
            continue

        if not old_exists:
            skipped_missing_source += 1
            plan.append(
                {
                    "version_id": version_id,
                    "document_id": row["document_id"],
                    "document_number": document_number,
                    "access_scope": access_scope,
                    "department_codes": department_codes,
                    "old_key": old_key,
                    "new_key": new_key,
                    "action": "skip",
                    "reason": "source_pdf_missing_in_r2",
                }
            )
            continue

        if new_exists_before and new_key != old_key:
            # New key already populated by some prior migration;
            # update DB only.
            plan.append(
                {
                    "version_id": version_id,
                    "document_id": row["document_id"],
                    "document_number": document_number,
                    "access_scope": access_scope,
                    "department_codes": department_codes,
                    "old_key": old_key,
                    "new_key": new_key,
                    "action": "update_db_only",
                    "reason": "new_key_present_in_r2",
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

        to_copy += 1
        plan.append(
            {
                "version_id": version_id,
                "document_id": row["document_id"],
                "document_number": document_number,
                "access_scope": access_scope,
                "department_codes": department_codes,
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

    manifest = {
        "apply": args.apply,
        "document_id_filter": args.document_id,
        "totals": {
            "rows_inspected": len(rows),
            "already_aligned": skipped_aligned,
            "to_copy": to_copy,
            "copied": copied,
            "missing_source": skipped_missing_source,
            "errors": len(errors),
        },
        "plan": [
            {
                **entry,
                "version_id": str(entry["version_id"]),
                "document_id": str(entry.get("document_id", "")),
            }
            for entry in plan
        ],
        "errors": [str(e) for e in errors],
    }

    manifest_path = Path(args.manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

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
