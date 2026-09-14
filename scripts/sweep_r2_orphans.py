#!/usr/bin/env python3
"""Sweep R2 for orphaned object keys.

Plan: approved "Reorganize R2 + Comprehensive E2E" §1.4.

For every key in the bucket, classify it against the canonical
layout + the live ``public.document_versions.object_key`` values:

* **live** — referenced by an active DB row.
* **legacy-pending** — matches a row's *old* key but the row's
  *current* ``object_key`` is now the new schema (post-migration,
  pre-cleanup).
* **orphan** — no DB row references it AND it's either non-canonical
  (UUID, seed, diagnostic prefix) or it doesn't match the current
  DB state for any row.

The script defaults to ``--dry-run``: prints the counts and a sample
list, writes ``sweep_manifest.json``. Pass ``--apply`` to bulk-delete
the orphans.

Usage::

    python scripts/sweep_r2_orphans.py
    python scripts/sweep_r2_orphans.py --apply
    python scripts/sweep_r2_orphans.py --keep-prefix=tests
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable

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
log = logging.getLogger("sweep_r2_orphans")


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


def _all_db_keys(engine: Any) -> set[str]:
    """Return every ``object_key`` currently in
    ``public.document_versions``.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT DISTINCT object_key "
                "FROM public.document_versions "
                "WHERE object_key IS NOT NULL"
            )
        ).all()
    return {str(r[0]) for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep R2 for orphaned keys (dry-run default)."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Bulk-delete orphans. Default is dry-run."
        ),
    )
    parser.add_argument(
        "--manifest",
        default="sweep_manifest.json",
        help="Path to the sweep manifest JSON.",
    )
    parser.add_argument(
        "--keep-prefix",
        action="append",
        default=[],
        help=(
            "Top-level prefix(es) to skip during sweep "
            "(e.g. 'tests'). Repeatable."
        ),
    )
    parser.add_argument(
        "--limit-sample",
        type=int,
        default=25,
        help="How many orphan keys to record as samples.",
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

    keep_prefixes: tuple[str, ...] = tuple(args.keep_prefix)
    db_keys = _all_db_keys(engine)
    log.info(
        "Discovered %d live DB object_keys", len(db_keys)
    )

    all_keys = r2.list_all_keys(prefixes=("",))
    log.info(
        "Discovered %d total object keys in bucket",
        len(all_keys),
    )

    live: list[str] = []
    legacy_pending: list[str] = []
    orphans: list[str] = []
    skipped: list[str] = []

    for key in all_keys:
        if any(
            key.startswith(prefix)
            for prefix in keep_prefixes
        ):
            skipped.append(key)
            continue

        if key in db_keys:
            live.append(key)
            continue

        # Is this a parsed canonical key that doesn't appear in DB?
        parsed = builder.parse(key)
        if parsed is not None:
            # Canonical shape but DB doesn't know about it. Treat as
            # orphan (likely a leftover from a test run or a write
            # that wasn't followed by a DB insert).
            orphans.append(key)
            continue

        # Non-canonical. Could be legacy-pending (matches a row's old
        # key from a previous version of code) or simply an orphan.
        # We can't disambiguate without history; treat any
        # non-canonical, non-DB key as orphan.
        orphans.append(key)

    # ``legacy-pending`` is a special case of orphan that maps to a
    # row whose *current* object_key is the new schema but whose old
    # key still exists. We approximate this: if a non-canonical key
    # shares a ``document_number`` (post-parse-fail attempt) with a
    # DB row, mark it legacy-pending. Without parsing, we just bucket
    # by exact DB-key set membership, so ``legacy-pending`` here is
    # only computable if a future run of migrate_r2_keys recorded
    # which old keys it migrated from. As a fallback we report the
    # full set as orphans; the human inspecting the manifest can
    # manually classify.
    legacy_pending = []

    sample = orphans[: args.limit_sample]
    manifest = {
        "apply": args.apply,
        "keep_prefixes": list(keep_prefixes),
        "totals": {
            "bucket_keys": len(all_keys),
            "live": len(live),
            "legacy_pending": len(legacy_pending),
            "orphans": len(orphans),
            "skipped": len(skipped),
            "db_keys": len(db_keys),
        },
        "sample_orphans": sample,
        "all_orphans_path": "orphans_to_delete.txt",
    }

    manifest_path = Path(args.manifest)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # Also write the full orphan list as a plain text file so the
    # operator can ``grep`` / ``cat`` it.
    orphans_file = Path(manifest["all_orphans_path"])
    orphans_file.write_text(
        "\n".join(orphans),
        encoding="utf-8",
    )

    print(json.dumps(manifest["totals"], indent=2))
    print(f"Manifest: {manifest_path}")
    print(f"Full orphan list: {orphans_file}")

    if args.apply:
        if not orphans:
            print("No orphans to delete.")
        else:
            errors = r2.delete_objects(orphans)
            print(
                f"Bulk-deleted {len(orphans) - len(errors)}"
                f" orphans; errors={len(errors)}"
            )
            if errors:
                errors_path = (
                    manifest_path.parent
                    / "sweep_errors.txt"
                )
                errors_path.write_text(
                    "\n".join(errors),
                    encoding="utf-8",
                )
                print(f"Errors written to: {errors_path}")
                return 1
    else:
        print(
            "Dry-run only. Re-run with --apply to commit."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())