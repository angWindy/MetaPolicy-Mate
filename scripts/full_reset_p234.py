#!/usr/bin/env python3
"""Full reset for P-234 — wipe Neon + Qdrant + R2 + reseed canonical data.

Plan reference: approved "Cleanup + Admin UI + RAG Redesign" §1.1.

This script is the standalone equivalent of ``scripts/e2e_full_smoke.py::phase_reset``
but stops at the data layer (no HTTP smoke). It is the destructive
companion to ``scripts/e2e_full_smoke.py`` — use this when you want to
nuke the demo from orbit and re-bootstrap from scratch.

Safety model:

* **dry-run by default** — never deletes anything until ``--apply``.
* Manifest is always written (even on dry-run) so an operator can
  audit what *would* happen before flipping ``--apply``.
* Refuses to run if ``app_env`` resolves to ``production`` in
  settings, unless ``--allow-production`` is passed.

Steps performed (in order, transactional per layer):

1. **Neon ``public.*``** — TRUNCATE 28 tables RESTART IDENTITY CASCADE.
2. **Neon ``rag_legacy.*``** — TRUNCATE 10 tables RESTART IDENTITY CASCADE.
3. **Qdrant** — drop + recreate the collection with dense+sparse
   vector config and 14 payload indexes.
4. **R2 (Cloudflare)** — list every object whose key starts with
   ``{tenant}/documents/`` then bulk-delete (batch size 1000).
5. **Reseed** — 2 departments, 4 roles, 13 permissions, 5 demo users,
   plus role-permission assignments. Idempotent on conflict.

Usage::

    python scripts/full_reset_p234.py                # dry-run, writes manifest
    python scripts/full_reset_p234.py --apply       # actually wipe
    python scripts/full_reset_p234.py --skip-r2     # skip R2 (CI without R2 creds)
    python scripts/full_reset_p234.py --skip-qdrant # skip Qdrant
    python scripts/full_reset_p234.py --keep-prefix=tests  # protect R2 prefix
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402

# Demo user UUIDs are derived from the user's email via UUIDv5 so the
# same email always resolves to the same ID across reseeds. The
# canonical source of the namespace and helper is scripts/_seed_ids.py.
from scripts._seed_ids import seed_user_id  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("full_reset_p234")

ARCHIVE_DIR = PROJECT_ROOT / "data" / "_archive"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical table list. MUST match database/schema.sql + every Alembic
# migration. Keep alphabetised for diff hygiene.
PUBLIC_TABLES: tuple[str, ...] = (
    "answer_feedbacks",
    "audit_logs",
    "audit_outbox",
    "chat_sessions",
    "chat_turns",
    "departments",
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
    "permissions",
    "refresh_tokens",
    "role_permissions",
    "roles",
    "static_thresholds",
    "user_activity_logs",
    "user_roles",
    "users",
)

RAG_LEGACY_TABLES: tuple[str, ...] = (
    "access_policies",
    "approval_records",
    "audit_logs",
    "chunks",
    "document_relations",
    "document_versions",
    "documents",
    "ingestion_jobs",
    "sections",
    "user_feedback",
)

# R2 prefix under which document blobs live. Every tenant prefix below
# this point is swept. Adjust here if ObjectKeyBuilder changes.
R2_DOCUMENT_PREFIXES: tuple[str, ...] = (
    "hust/documents/",
    "huce/documents/",
)

# Qdrant payload indexes — keep in sync with scripts/e2e_full_smoke.py
# (the canonical create_payload_index list).
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


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------


def _load_env() -> dict[str, str]:
    """Load .env.rag then .env without polluting os.environ permanently.

    The script reads every setting via this dict rather than relying on
    get_settings() so it can be invoked from CI containers that lack a
    fully-populated environment. Values are taken verbatim from the
    files.
    """
    env: dict[str, str] = {}
    for path in (".env.rag", ".env"):
        if not Path(path).exists():
            continue
        for k, v in dotenv_values(path).items():
            if v is None:
                continue
            env.setdefault(k, v)
    # Allow process env to override (e.g. CI secrets).
    for k, v in os.environ.items():
        env[k] = v
    return env


def _require(env: dict[str, str], key: str) -> str:
    if key not in env or not env[key]:
        raise SystemExit(
            f"ERROR: required env var '{key}' is missing. "
            f"Set it in .env / .env.rag or as a process env var."
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


# ---------------------------------------------------------------------------
# Result accumulator
# ---------------------------------------------------------------------------


@dataclass
class ResetManifest:
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str = ""
    apply: bool = False
    app_env: str = "?"
    database_url_host: str = "?"
    qdrant_collection: str = ""
    r2_bucket: str = ""
    public_tables_truncated: list[str] = field(default_factory=list)
    rag_legacy_tables_truncated: list[str] = field(default_factory=list)
    qdrant_collection_state: str = ""
    r2_keys_scanned: int = 0
    r2_keys_deleted: int = 0
    r2_errors: list[str] = field(default_factory=list)
    demo_users_seeded: int = 0
    departments_seeded: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Step 1: Neon wipe + reseed
# ---------------------------------------------------------------------------


def _host_from_url(url: str) -> str:
    # Mask credentials and path; keep only @host:port.
    m = re.search(r"@([\w.\-:\[\]]+)", url)
    return m.group(1) if m else "?"


def reset_neon(
    db_url: str,
    manifest: ResetManifest,
    apply: bool,
) -> Engine:
    """TRUNCATE both schemas, then reseed canonical reference data.

    Returns the live engine (caller is responsible for ``.dispose()``).
    """
    engine = create_engine(_to_psycopg_url(db_url))
    manifest.database_url_host = _host_from_url(db_url)

    with engine.connect() as conn:
        # Ensure rag_legacy schema exists (idempotent — create_all in
        # step 1.5 would otherwise fail if public truncate removed
        # dependents first).
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS rag_legacy"))
        conn.commit()

    if apply:
        with engine.connect() as conn:
            joined_public = ", ".join(f"public.{t}" for t in PUBLIC_TABLES)
            conn.execute(
                text(
                    f"TRUNCATE TABLE {joined_public} "
                    "RESTART IDENTITY CASCADE"
                )
            )
            joined_rag = ", ".join(
                f"rag_legacy.{t}" for t in RAG_LEGACY_TABLES
            )
            conn.execute(
                text(
                    f"TRUNCATE TABLE {joined_rag} "
                    "RESTART IDENTITY CASCADE"
                )
            )
            conn.commit()
        manifest.public_tables_truncated = list(PUBLIC_TABLES)
        manifest.rag_legacy_tables_truncated = list(RAG_LEGACY_TABLES)
        log.info(
            "Neon truncated: %d public + %d rag_legacy tables",
            len(PUBLIC_TABLES),
            len(RAG_LEGACY_TABLES),
        )
        # Give the connection pool a beat to release idle conns before
        # the next layer opens its own (mirrors e2e_full_smoke phase_reset).
        time.sleep(1.5)
    else:
        log.info(
            "DRY RUN — would truncate %d public + %d rag_legacy tables",
            len(PUBLIC_TABLES),
            len(RAG_LEGACY_TABLES),
        )

    if apply:
        _reseed_canonical(engine, manifest)
    else:
        log.info("DRY RUN — would reseed 2 departments + 4 roles + 5 users")

    return engine


def _reseed_canonical(engine: Engine, manifest: ResetManifest) -> None:
    """Insert the canonical RBAC + tenant reference data.

    Stable UUIDs are used so any downstream integration tests, JWT
    fixtures, or demo data can refer to them deterministically. The
    canonical source of these UUIDs is ``scripts/_seed_ids.py`` — same
    email always maps to the same UUID. Mirrors
    scripts/e2e_full_smoke.py::phase_reset § "Reseed reference data".
    """
    import bcrypt as _bcrypt

    hust_id = "cc8dc08f-3f47-4fd9-9cf5-8e7443b17b2c"
    huce_id = "050813ff-d105-4b95-aab2-fe8c7e3a33f7"
    admin_role_id = "00000000-0000-0000-0000-000000000001"
    user_role_id = "00000000-0000-0000-0000-000000000002"
    leader_role_id = "00000000-0000-0000-0000-000000000003"
    reviewer_role_id = "00000000-0000-0000-0000-000000000004"

    # User UUIDs are derived from the user's email via UUIDv5 so that the
    # same email always resolves to the same ID across reseeds (see
    # scripts/_seed_ids.py for the stability contract).
    admin_user_id = str(seed_user_id("admin@p234.demo"))
    hust_user_id = str(seed_user_id("hust@p234.demo"))
    huce_user_id = str(seed_user_id("huce@p234.demo"))
    cross_user_id = str(seed_user_id("crossschool@p234.demo"))
    reviewer_user_id = str(seed_user_id("reviewer@p234.demo"))

    pw_hash = _bcrypt.hashpw(b"P234@123", _bcrypt.gensalt()).decode("utf-8")

    perm_ids = {
        "document_read": "10000000-0000-0000-0000-000000000001",
        "document_upload": "10000000-0000-0000-0000-000000000002",
        "document_update": "10000000-0000-0000-0000-000000000003",
        "document_delete": "10000000-0000-0000-0000-000000000004",
        "chat_use": "10000000-0000-0000-0000-000000000005",
        "user_read": "10000000-0000-0000-0000-000000000006",
        "user_manage": "10000000-0000-0000-0000-000000000007",
        "document_approve": "10000000-0000-0000-0000-000000000008",
        "document_process": "10000000-0000-0000-0000-000000000009",
        "document_audit_read": "10000000-0000-0000-0000-00000000000a",
        "activity_log_read": "10000000-0000-0000-0000-00000000000b",
        "rbac_manage": "10000000-0000-0000-0000-00000000000c",
        "role_manage": "10000000-0000-0000-0000-00000000000d",
    }

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.departments (id, name, code, is_active)
                VALUES
                  (:hust_id, 'Trường Đại học Bách khoa Hà Nội', 'HUST', true),
                  (:huce_id, 'Trường Đại học Kiến trúc Hà Nội', 'HUCE', true)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"hust_id": hust_id, "huce_id": huce_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO public.roles (id, code, name, is_system) VALUES
                  (:admin_role_id, 'ADMIN', 'Administrator', true),
                  (:user_role_id, 'USER', 'User', true),
                  (:leader_role_id, 'LEADER', 'Leader (legacy)', false),
                  (:reviewer_role_id, 'REVIEWER', 'Reviewer (legacy)', false)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "admin_role_id": admin_role_id,
                "user_role_id": user_role_id,
                "leader_role_id": leader_role_id,
                "reviewer_role_id": reviewer_role_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO public.permissions
                  (id, code, name, module) VALUES
                  (:document_read,       'document.read',       'Read documents',          'document'),
                  (:document_upload,      'document.upload',     'Upload documents',        'document'),
                  (:document_update,      'document.update',     'Update documents',        'document'),
                  (:document_delete,      'document.delete',     'Delete documents',        'document'),
                  (:chat_use,             'chat.use',            'Use chatbot',             'chat'),
                  (:user_read,            'user.read',           'Read users',              'user'),
                  (:user_manage,          'user.manage',         'Manage users',            'user'),
                  (:document_approve,     'document.approve',    'Approve documents',       'document'),
                  (:document_process,     'document.process',    'Process documents',       'document'),
                  (:document_audit_read,  'document.audit.read', 'Read audit data',         'document'),
                  (:activity_log_read,    'activity_log.read',   'Read activity logs',      'activity'),
                  (:rbac_manage,          'rbac.manage',         'Manage RBAC',             'rbac'),
                  (:role_manage,          'role.manage',         'Manage roles',            'rbac')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            perm_ids,
        )
        rp_rows = text(
            """
            INSERT INTO public.role_permissions (role_id, permission_id)
            VALUES (:rid, :pid)
            ON CONFLICT DO NOTHING
            """
        )
        role_perms = {
            admin_role_id: [
                "document_read", "document_upload", "document_update",
                "document_delete", "document_approve", "document_process",
                "document_audit_read", "activity_log_read", "chat_use",
                "user_read", "user_manage", "rbac_manage", "role_manage",
            ],
            user_role_id: [
                "document_read", "document_upload",
                "document_process", "document_approve",
                "document_audit_read", "activity_log_read",
                "chat_use", "user_read",
            ],
            leader_role_id: [
                "document_read", "document_upload",
                "document_approve", "document_audit_read",
                "activity_log_read", "chat_use", "user_read",
            ],
            reviewer_role_id: [
                "document_read", "document_upload",
                "document_process", "chat_use",
            ],
        }
        for rid, codes in role_perms.items():
            for code in codes:
                conn.execute(
                    rp_rows,
                    {"rid": rid, "pid": perm_ids[code]},
                )

        demo_users = [
            (admin_user_id, "admin@p234.demo", hust_id, admin_role_id),
            (hust_user_id, "hust@p234.demo", hust_id, user_role_id),
            (huce_user_id, "huce@p234.demo", huce_id, user_role_id),
            (cross_user_id, "crossschool@p234.demo", None, admin_role_id),
            (
                reviewer_user_id,
                "reviewer@p234.demo",
                huce_id,
                reviewer_role_id,
            ),
        ]
        for uid, email, dept_id, role_id in demo_users:
            conn.execute(
                text(
                    """
                    INSERT INTO public.users (
                      id, email, password_hash, full_name,
                      department_id, token_version, is_active
                    ) VALUES (
                      :uid, :email, :pw_hash, :full_name,
                      :dept_id, 1, true
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "uid": uid,
                    "email": email,
                    "pw_hash": pw_hash,
                    "full_name": email.split("@")[0].title(),
                    "dept_id": dept_id,
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO public.user_roles (user_id, role_id) VALUES
                      (:uid, :rid)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"uid": uid, "rid": role_id},
            )
        conn.commit()

    manifest.departments_seeded = ["HUST", "HUCE"]
    manifest.demo_users_seeded = len(demo_users)
    log.info(
        "Reseeded: 2 departments, 4 roles, %d role-perm rows, %d users",
        sum(len(c) for c in role_perms.values()),
        len(demo_users),
    )


# ---------------------------------------------------------------------------
# Step 2: Qdrant reset
# ---------------------------------------------------------------------------


def reset_qdrant(
    env: dict[str, str],
    manifest: ResetManifest,
    apply: bool,
    skip: bool,
) -> None:
    """Drop + recreate the Qdrant collection with dense+sparse config.

    Reads ``QDRANT_URL`` / ``QDRANT_API_KEY`` / ``QDRANT_COLLECTION`` /
    ``EMBEDDING_DIMENSIONS`` from the loaded env (matching the RAG
    module's :class:`RAGSettings`).
    """
    if skip:
        log.info("Qdrant: skipped (--skip-qdrant)")
        manifest.qdrant_collection_state = "skipped"
        return

    qdrant_url = _require(env, "QDRANT_URL")
    qdrant_api_key = env.get("QDRANT_API_KEY", "") or None
    collection = _require(env, "QDRANT_COLLECTION")
    vector_size = int(env.get("EMBEDDING_DIMENSIONS", "1536"))

    manifest.qdrant_collection = collection

    # Imported lazily so the script can run with --skip-qdrant even
    # when qdrant_client isn't installed (test envs).
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    existing = {c.name for c in client.get_collections().collections}

    if not apply:
        log.info(
            "DRY RUN — would drop+recreate Qdrant collection '%s' "
            "(size=%d, dense+sparse)",
            collection,
            vector_size,
        )
        manifest.qdrant_collection_state = (
            "would_recreate" if collection in existing else "would_create"
        )
        return

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
    log.info(
        "Qdrant collection recreated: %s (size=%d, dense+sparse)",
        collection,
        vector_size,
    )

    for field_name, schema_type in QDRANT_PAYLOAD_INDEXES:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=getattr(qmodels.PayloadSchemaType, schema_type.upper()),
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("payload index %s: %s", field_name, exc)
    log.info(
        "Qdrant payload indexes created: %d fields",
        len(QDRANT_PAYLOAD_INDEXES),
    )
    manifest.qdrant_collection_state = "recreated"


# ---------------------------------------------------------------------------
# Step 3: R2 wipe
# ---------------------------------------------------------------------------


def reset_r2(
    env: dict[str, str],
    manifest: ResetManifest,
    apply: bool,
    skip: bool,
    keep_prefixes: list[str],
) -> None:
    """List every document blob in R2 and bulk-delete.

    Only touches keys under ``R2_DOCUMENT_PREFIXES`` (i.e. per-tenant
    document roots). Other prefixes (e.g. ``tests/``) are left alone
    unless explicitly added to ``keep_prefixes`` (or as extra targets
    via ``--r2-prefix``).
    """
    if skip:
        log.info("R2: skipped (--skip-r2)")
        manifest.r2_keys_scanned = 0
        return

    endpoint = _require(env, "R2_ENDPOINT")
    access_key = _require(env, "R2_ACCESS_KEY_ID")
    secret_key = _require(env, "R2_SECRET_ACCESS_KEY")
    bucket = _require(env, "R2_BUCKET_NAME")
    manifest.r2_bucket = bucket

    from scripts._r2_maintenance import R2Maintenance

    r2 = R2Maintenance(
        endpoint=endpoint,
        access_key_id=access_key,
        secret_access_key=secret_key,
        bucket_name=bucket,
    )

    targets = list(R2_DOCUMENT_PREFIXES) + [
        p for p in keep_prefixes if p.endswith("/")
    ]
    keys = r2.list_all_keys(prefixes=targets)

    # Also keep anything under user-supplied keep prefixes.
    keep_set: set[str] = set()
    for kp in keep_prefixes:
        if not kp.endswith("/"):
            continue
        for entry in r2.list_objects(kp):
            key = entry.get("Key")
            if key:
                keep_set.add(str(key))
    to_delete = [k for k in keys if k not in keep_set]

    manifest.r2_keys_scanned = len(keys)
    log.info(
        "R2 bucket '%s' scanned: %d keys under %s, %d to delete",
        bucket,
        len(keys),
        list(targets),
        len(to_delete),
    )

    if not apply:
        log.info("DRY RUN — would bulk-delete %d R2 objects", len(to_delete))
        return

    if not to_delete:
        log.info("R2 nothing to delete")
        return

    errors = r2.delete_objects(to_delete)
    manifest.r2_keys_deleted = len(to_delete) - len(errors)
    manifest.r2_errors = errors
    if errors:
        log.error(
            "R2 delete reported %d errors (sample=%s)",
            len(errors),
            errors[:5],
        )
    else:
        log.info("R2 bulk-deleted %d objects", manifest.r2_keys_deleted)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _check_production(env: dict[str, str], allow: bool) -> None:
    """Refuse to wipe in production unless explicitly allowed."""
    app_env = env.get("APP_ENV", "development").lower()
    if app_env == "production" and not allow:
        raise SystemExit(
            "ERROR: APP_ENV=production detected. Refusing to wipe. "
            "Pass --allow-production to override (not recommended)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Full reset of P-234 — wipe Neon + Qdrant + R2 + reseed. "
            "Dry-run by default; pass --apply to commit."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete data. Default is dry-run.",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant wipe (e.g. CI without Qdrant).",
    )
    parser.add_argument(
        "--skip-r2",
        action="store_true",
        help="Skip R2 wipe (e.g. CI without R2 credentials).",
    )
    parser.add_argument(
        "--skip-neon",
        action="store_true",
        help="Skip Neon truncate + reseed.",
    )
    parser.add_argument(
        "--keep-prefix",
        action="append",
        default=[],
        help=(
            "Extra R2 prefix(es) to protect (e.g. 'tests/'). "
            "Repeatable."
        ),
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Override the production safety check.",
    )
    parser.add_argument(
        "--manifest",
        default=str(ARCHIVE_DIR / "full_reset_manifest.json"),
        help="Path to the JSON manifest output.",
    )
    args = parser.parse_args()

    env = _load_env()
    _check_production(env, args.allow_production)

    manifest = ResetManifest(apply=args.apply, app_env=env.get("APP_ENV", "?"))

    log.info(
        "Starting full_reset_p234 (apply=%s, app_env=%s)",
        args.apply,
        manifest.app_env,
    )

    engine: Engine | None = None
    try:
        if not args.skip_neon:
            db_url = _require(env, "DATABASE_URL")
            engine = reset_neon(db_url, manifest, args.apply)
        else:
            log.info("Neon: skipped (--skip-neon)")
        reset_qdrant(env, manifest, args.apply, args.skip_qdrant)
        reset_r2(env, manifest, args.apply, args.skip_r2, args.keep_prefix)
    except Exception as exc:  # noqa: BLE001
        manifest.errors.append(f"{type(exc).__name__}: {exc}")
        log.exception("Reset failed")
    finally:
        if engine is not None:
            engine.dispose()
        manifest.finish()

    # Always write the manifest, even on failure, so an operator can
    # inspect what state the system is in.
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    log.info("Manifest: %s", manifest_path)

    if manifest.errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
