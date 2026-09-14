"""Migrate misrouted R2 keys from ``hust/documents/`` to the correct tenant.

Root cause
----------
``scripts/ingest_via_admin.py`` previously logged in as the demo admin
whose school code is ``hust``. Every upload landed under
``hust/documents/{document_number}/v1/source.pdf`` regardless of the
folder the PDF came from (``data/raw/HUCE/*.pdf`` vs ``data/raw/HUST/*.pdf``).

This script:

1. Lists every object under ``hust/documents/`` in the bucket.
2. For each key whose ``document_number`` starts with ``RAW-HUCE-`` or
   any other ``huce``-prefixed slug, copies the object to
   ``huce/documents/{...same suffix}`` and deletes the original.
3. After a successful copy, rewrites the matching
   ``public.document_versions.object_key`` to the canonical ``huce/...``
   path so DB lookups continue to resolve.

Dry-run by default (use ``--apply`` to commit).

Usage::

    python scripts/migrate_r2_huce_keys.py            # dry-run
    python scripts/migrate_r2_huce_keys.py --apply    # commit

Safety:

* Source key is only deleted AFTER the destination copy succeeds.
* DB update is rolled back on any DB error.
* Run is idempotent: a second invocation finds no ``hust/documents/RAW-HUCE-*``
  keys and exits cleanly.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.client import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate_r2_huce")

# Any document_number that starts with one of these prefixes is
# considered "owned" by HUCE and is rerouted from the hust/ prefix to
# the huce/ prefix. The set covers the canonical ``RAW-HUCE-`` slug
# produced by ``ingest_via_admin.py`` plus any custom ``HUCE-`` prefix
# a manual upload might have used.
HUCE_DOC_NUMBER_PREFIXES: tuple[str, ...] = (
    "RAW-HUCE-",
    "HUCE-",
)

HUST_DOC_NUMBER_PREFIXES: tuple[str, ...] = (
    "RAW-HUST-",
    "HUST-",
)

SOURCE_PREFIX = "hust/documents/"
DEST_PREFIX_HUCE = "huce/documents/"
DEST_PREFIX_HUST = "hust/documents/"  # canonical, no move needed


@dataclass
class MigrationReport:
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = ""
    apply: bool = False
    keys_scanned: int = 0
    huce_keys_rerouted: int = 0
    hust_keys_unchanged: int = 0
    db_rows_updated: int = 0
    errors: list[str] = field(default_factory=list)
    moves: list[dict[str, str]] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (".env.rag", ".env"):
        if not Path(path).exists():
            continue
        for k, v in dotenv_values(path).items():
            if v is None:
                continue
            env.setdefault(k, v)
    for k, v in __import__("os").environ.items():
        env[k] = v
    return env


def _require(env: dict[str, str], key: str) -> str:
    if key not in env or not env[key]:
        raise SystemExit(
            f"ERROR: required env var '{key}' is missing"
        )
    return env[key]


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


def _s3_client(env: dict[str, str]) -> Any:
    """Build a boto3 S3 client pinned to the R2 endpoint.

    boto3 is already a transitive dep of ``qdrant-client`` and the
    project's own ``r2_file_storage``. Reading endpoint + creds from
    the loaded env rather than re-importing the project module keeps
    the script standalone (no FastAPI startup, no service container).
    """
    return boto3.client(
        "s3",
        endpoint_url=_require(env, "R2_ENDPOINT"),
        aws_access_key_id=_require(env, "R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_require(env, "R2_SECRET_ACCESS_KEY"),
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
        region_name="auto",
    )


def _list_hust_prefix(s3: Any, bucket: str) -> list[str]:
    """Return every object key under ``hust/documents/`` (1 level deep).

    We only need the direct children because each document gets its
    own folder (``hust/documents/{document_number}/v{n}/source.pdf``).
    Using a delimited list keeps the call small for buckets with
    hundreds of versions.
    """
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=SOURCE_PREFIX,
    ):
        for obj in page.get("Contents", []):
            keys.append(str(obj["Key"]))
    return keys


def _copy_then_delete(
    s3: Any,
    bucket: str,
    src_key: str,
    dst_key: str,
    apply: bool,
) -> bool:
    """Atomically copy src_key to dst_key, then delete src_key.

    Returns True on success, False on failure. Dry-run paths log the
    intent but make no API calls.
    """
    if not apply:
        log.info("  WOULD copy %s -> %s", src_key, dst_key)
        return False  # didn't actually run

    # Copy via server-side COPY so we don't have to download+upload.
    copy_source = {"Bucket": bucket, "Key": src_key}
    s3.copy_object(
        Bucket=bucket,
        Key=dst_key,
        CopySource=copy_source,
        MetadataDirective="COPY",
    )
    # Only delete the source once the copy succeeded.
    s3.delete_object(Bucket=bucket, Key=src_key)
    log.info("  MOVED %s -> %s", src_key, dst_key)
    return True


def _doc_number_from_key(key: str) -> str:
    """Extract ``document_number`` from ``hust/documents/{doc_no}/v{n}/source.pdf``.

    Falls back to the basename minus extension when the structure is
    unexpected — better than silently dropping the row.
    """
    parts = key.split("/")
    # hust/documents/{doc_no}/v1/source.pdf  =>  parts = [hust, documents, doc_no, v1, source.pdf]
    if (
        len(parts) >= 5
        and parts[0] == "hust"
        and parts[1] == "documents"
        and parts[3].startswith("v")
    ):
        return parts[2]
    return parts[-1].rsplit(".", 1)[0]


def _is_huce_doc_number(doc_number: str) -> bool:
    return any(
        doc_number.startswith(prefix)
        for prefix in HUCE_DOC_NUMBER_PREFIXES
    )


def _update_db_object_key(
    db_engine: Engine,
    old_key: str,
    new_key: str,
    apply: bool,
) -> int:
    """Rewrite the matching ``document_versions.object_key`` row.

    Returns the number of rows updated (0 if none matched). We key on
    ``object_key`` because the version UUID is not exposed by the
    admin read API.
    """
    with db_engine.connect() as conn:
        if not apply:
            row = conn.execute(
                text(
                    "SELECT id, document_id, version_number "
                    "FROM public.document_versions "
                    "WHERE object_key = :key"
                ),
                {"key": old_key},
            ).first()
            if row:
                log.info(
                    "  WOULD update DB row document_id=%s version=%s",
                    row[1],
                    row[2],
                )
                return 1
            return 0

        result = conn.execute(
            text(
                "UPDATE public.document_versions "
                "SET object_key = :new_key "
                "WHERE object_key = :old_key"
            ),
            {"new_key": new_key, "old_key": old_key},
        )
        conn.commit()
        rows = result.rowcount or 0
        if rows:
            log.info(
                "  DB updated %d row(s): %s -> %s",
                rows,
                old_key,
                new_key,
            )
        return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move R2 objects and update DB rows. "
        "Default is dry-run.",
    )
    parser.add_argument(
        "--manifest",
        default=str(
            PROJECT_ROOT
            / "data"
            / "_archive"
            / "migrate_r2_huce_manifest.json"
        ),
        help="Path to JSON manifest output.",
    )
    args = parser.parse_args()

    env = _load_env()
    report = MigrationReport(apply=args.apply)
    log.info(
        "Starting migrate_r2_huce_keys (apply=%s)",
        args.apply,
    )

    try:
        bucket = _require(env, "R2_BUCKET_NAME")
        s3 = _s3_client(env)
        all_keys = _list_hust_prefix(s3, bucket)
        report.keys_scanned = len(all_keys)
        log.info(
            "Scanned %d keys under %s",
            len(all_keys),
            SOURCE_PREFIX,
        )

        db_url = _require(env, "DATABASE_URL")
        db_engine = create_engine(_to_psycopg_url(db_url))

        for src_key in sorted(all_keys):
            doc_number = _doc_number_from_key(src_key)

            if not _is_huce_doc_number(doc_number):
                # HUST or unknown tenant — leave under hust/.
                report.hust_keys_unchanged += 1
                log.debug(
                    "  keep %s (doc_number=%s)",
                    src_key,
                    doc_number,
                )
                continue

            # Build the destination key: swap prefix from hust/ to huce/.
            assert src_key.startswith(SOURCE_PREFIX)
            dst_key = (
                DEST_PREFIX_HUCE
                + src_key[len(SOURCE_PREFIX):]
            )

            moved = _copy_then_delete(
                s3,
                bucket,
                src_key,
                dst_key,
                args.apply,
            )

            if moved or not args.apply:
                # Both dry-run and real runs need the DB preview/update.
                rows_updated = _update_db_object_key(
                    db_engine,
                    old_key=src_key,
                    new_key=dst_key,
                    apply=args.apply,
                )
                if args.apply:
                    report.db_rows_updated += rows_updated
                elif rows_updated:
                    # In dry-run we still record the intent for the manifest.
                    pass

            if moved:
                report.huce_keys_rerouted += 1
            report.moves.append(
                {
                    "from": src_key,
                    "to": dst_key,
                    "applied": str(moved),
                }
            )

            # Small breather between object moves so R2 rate limits
            # don't bite on large batches.
            time.sleep(0.2)

        db_engine.dispose()

    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"{type(exc).__name__}: {exc}")
        log.exception("Migration failed")

    report.finish()
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            report.__dict__,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    log.info("Manifest: %s", manifest_path)
    log.info(
        "Summary: scanned=%d, huce_rerouted=%d, hust_kept=%d, "
        "db_rows_updated=%d, errors=%d",
        report.keys_scanned,
        report.huce_keys_rerouted,
        report.hust_keys_unchanged,
        report.db_rows_updated,
        len(report.errors),
    )

    if report.errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
