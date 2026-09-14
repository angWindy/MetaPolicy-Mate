"""Targeted document-only reset.

Wipes only document + chat tables from public schema (NOT users/auth)
so users don't lose their sessions. Also wipes the Qdrant collection
and R2 document prefixes.

Usage::

    python scripts/reset_documents_only.py            # dry-run
    python scripts/reset_documents_only.py --apply    # commit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("reset_documents_only")

# Document + chat tables to wipe. Order matters because of FKs — children
# before parents.
DOCUMENT_TABLES: tuple[str, ...] = (
    "answer_feedbacks",
    "audit_outbox",
    "chat_turns",
    "chat_sessions",
    "document_application_scopes",
    "document_chunks",
    "document_cross_reference_drafts",
    "document_departments",
    "document_effectiveness_alerts",
    "document_ingestion_jobs",
    "document_metadata_drafts",
    "document_relations",
    "document_section_metadata_drafts",
    "document_section_versions",
    "document_sections",
    "document_versions",
    "documents",
    "static_thresholds",
)

R2_DOCUMENT_PREFIXES: tuple[str, ...] = (
    "hust/documents/",
    "huce/documents/",
)

QDRANT_PAYLOAD_INDEXES: tuple[tuple[str, str], ...] = (
    ("tenant_id", "keyword"),
    ("document_id", "keyword"),
    ("version_id", "keyword"),
    ("chunk_id", "keyword"),
    ("owner_unit", "keyword"),
    ("allowed_roles", "keyword"),
    ("allowed_units", "keyword"),
    ("classification", "keyword"),
    ("status", "keyword"),
    ("legal_status", "keyword"),
    ("valid_from", "datetime"),
    ("valid_to", "datetime"),
    ("page", "integer"),
    ("section", "keyword"),
)


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


def _to_psycopg_url(db_url: str) -> str:
    if db_url.startswith("postgresql+psycopg://"):
        return db_url
    if db_url.startswith("postgresql+psycopg2://"):
        return db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return db_url


def _require(env: dict[str, str], key: str) -> str:
    if key not in env or not env[key]:
        raise SystemExit(f"ERROR: required env var '{key}' is missing")
    return env[key]


def wipe_documents(
    db_url: str,
    apply: bool,
) -> dict[str, object]:
    """Truncate all document-related tables (CASCADE).

    Only touches tables related to documents and chats; users, auth,
    roles, permissions, departments are preserved.
    """
    engine = create_engine(_to_psycopg_url(db_url))
    manifest: dict[str, object] = {
        "tables_truncated": [],
        "table_counts_before": {},
    }

    with engine.connect() as conn:
        # Snapshot counts first so the manifest can show what was wiped.
        for table in DOCUMENT_TABLES:
            row = conn.execute(
                text(f"SELECT COUNT(*) FROM public.{table}")
            ).first()
            manifest["table_counts_before"][table] = (
                row[0] if row else 0
            )

        if not apply:
            log.info(
                "DRY RUN — would truncate %d document tables: %s",
                len(DOCUMENT_TABLES),
                ", ".join(DOCUMENT_TABLES),
            )
            return manifest

        joined = ", ".join(f"public.{t}" for t in DOCUMENT_TABLES)
        conn.execute(
            text(
                f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()
        log.info(
            "Truncated %d document tables: %s",
            len(DOCUMENT_TABLES),
            ", ".join(DOCUMENT_TABLES),
        )
        manifest["tables_truncated"] = list(DOCUMENT_TABLES)
        time.sleep(1.5)

    engine.dispose()
    return manifest


def wipe_qdrant(
    env: dict[str, str],
    apply: bool,
) -> str:
    """Drop + recreate the Qdrant collection."""
    qdrant_url = _require(env, "QDRANT_URL")
    qdrant_api_key = env.get("QDRANT_API_KEY", "") or None
    collection = _require(env, "QDRANT_COLLECTION")
    vector_size = int(env.get("EMBEDDING_DIMENSIONS", "1536"))

    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    existing = {c.name for c in client.get_collections().collections}

    if not apply:
        log.info(
            "DRY RUN — would drop+recreate Qdrant collection '%s'",
            collection,
        )
        return (
            "would_recreate" if collection in existing else "would_create"
        )

    if collection in existing:
        client.delete_collection(collection_name=collection)
        log.info("Qdrant collection deleted: %s", collection)
        time.sleep(1.5)

    client.create_collection(
        collection_name=collection,
        vectors_config={
            "dense": qmodels.VectorParams(
                size=vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "sparse": qmodels.SparseVectorParams(
                index=qmodels.SparseIndexParams(on_disk=False),
            ),
        },
        on_disk_payload=True,
    )
    for field_name, schema_type in QDRANT_PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=getattr(
                    qmodels.PayloadSchemaType, schema_type.upper()
                ),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("payload index %s: %s", field_name, exc)
    log.info(
        "Qdrant collection recreated with %d payload indexes",
        len(QDRANT_PAYLOAD_INDEXES),
    )
    return "recreated"


def wipe_r2(
    env: dict[str, str],
    apply: bool,
) -> dict[str, int]:
    """Delete every object under R2_DOCUMENT_PREFIXES."""
    endpoint = _require(env, "R2_ENDPOINT")
    access_key = _require(env, "R2_ACCESS_KEY_ID")
    secret_key = _require(env, "R2_SECRET_ACCESS_KEY")
    bucket = _require(env, "R2_BUCKET_NAME")

    from scripts._r2_maintenance import R2Maintenance

    r2 = R2Maintenance(
        endpoint=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        bucket_name=bucket,
    )

    keys = r2.list_all_keys(prefixes=list(R2_DOCUMENT_PREFIXES))
    log.info(
        "R2 scanned: %d keys under %s",
        len(keys),
        list(R2_DOCUMENT_PREFIXES),
    )

    if not apply:
        log.info("DRY RUN — would delete %d R2 objects", len(keys))
        return {"scanned": len(keys), "deleted": 0}

    if not keys:
        return {"scanned": 0, "deleted": 0}

    errors = r2.delete_objects(keys)
    deleted = len(keys) - len(errors)
    log.info(
        "R2 deleted %d/%d objects (errors=%d)",
        deleted,
        len(keys),
        len(errors),
    )
    return {"scanned": len(keys), "deleted": deleted}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete data. Default is dry-run.",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant wipe",
    )
    parser.add_argument(
        "--skip-r2",
        action="store_true",
        help="Skip R2 wipe",
    )
    args = parser.parse_args()

    env = _load_env()
    started = datetime.now(timezone.utc).isoformat()
    log.info("Starting reset_documents_only (apply=%s)", args.apply)

    manifest: dict[str, object] = {
        "started_at": started,
        "apply": args.apply,
        "documents": {},
        "qdrant": {},
        "r2": {},
    }

    try:
        db_url = _require(env, "DATABASE_URL")
        manifest["documents"] = wipe_documents(db_url, args.apply)

        if args.skip_qdrant:
            manifest["qdrant"] = "skipped"
        else:
            manifest["qdrant"] = wipe_qdrant(env, args.apply)

        if args.skip_r2:
            manifest["r2"] = "skipped"
        else:
            manifest["r2"] = wipe_r2(env, args.apply)
    except Exception as exc:  # noqa: BLE001
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        log.exception("Reset failed")
        archive = PROJECT_ROOT / "data" / "_archive" / "reset_documents_manifest.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, default=str)
        )
        return 1

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    archive = PROJECT_ROOT / "data" / "_archive" / "reset_documents_manifest.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str)
    )
    log.info("Manifest: %s", archive)
    log.info("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
