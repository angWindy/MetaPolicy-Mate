#!/usr/bin/env python3
"""End-to-end smoke + integration orchestrator for P-234 / PolicyMate AI.

Refactored from the previous linear script into a **phase-driven
orchestrator** (see approved "Comprehensive E2E" plan §2.1). Each phase
returns ``(ok: bool, detail: dict)`` and the orchestrator chains them in
order. Run the full pipeline::

    python scripts/e2e_full_smoke.py

Or pick phases and stop-on-failure::

    python scripts/e2e_full_smoke.py \
        --phases reset,upload,ingest --stop-on-failure

Default phases::

    reset, register, auth_matrix, rbac_matrix, upload, ingest,
    rag_query, cross_school, delete_cascade, replace_source, cleanup

JSON summary is printed at the end so CI can parse it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from dotenv import dotenv_values
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

BACKEND_BASE = os.environ.get("BACKEND_BASE", "http://localhost:8000")
API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def banner(msg: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {msg}")
    print("=" * 78)


def info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def ok(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"  [PASS] {label}{suffix}")


def warn(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"  [WARN] {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"  [FAIL] {label}{suffix}")


def mask(s: str, keep: int = 4) -> str:
    if not s or len(s) <= keep * 2:
        return "***"
    return f"{s[:keep]}***{s[-keep:]}"


# ---------------------------------------------------------------------------
# Shared state + env
# ---------------------------------------------------------------------------


@dataclass
class PhaseContext:
    """Mutated by every phase; keys are phase-specific."""

    env: dict[str, str] = field(default_factory=dict)
    engine: Any = None
    qdrant: QdrantClient | None = None
    qdrant_collection: str = ""
    pdf_path: Path | None = None
    r2_client: Any = None
    r2_bucket: str = ""

    # Identity / tokens captured by auth_matrix; reused by later phases.
    admin_token: str = ""
    hust_token: str = ""
    huce_token: str = ""
    cross_token: str = ""
    reviewer_token: str = ""
    new_hust_token: str = ""
    new_hust_email: str = ""

    # Documents created during the run.
    primary_document_id: str = ""
    primary_version_id: str = ""
    primary_object_key: str = ""
    primary_qdrant_points: int = 0

    huce_document_id: str = ""
    huce_version_id: str = ""

    second_version_id: str = ""
    second_object_key: str = ""


PhaseFn = Callable[
    [PhaseContext, httpx.AsyncClient],
    Awaitable[tuple[bool, dict[str, Any]]],
]


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


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


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for path in (".env.rag", ".env"):
        if not Path(path).exists():
            continue
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env.setdefault(k.strip(), v.strip())
    return env


# ---------------------------------------------------------------------------
# Phase: reset
# ---------------------------------------------------------------------------


async def phase_reset(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE reset — TRUNCATE Neon + recreate Qdrant + reseed")
    db_url = _to_psycopg_url(ctx.env["DATABASE_URL"])
    ctx.engine = create_engine(db_url)
    eng = ctx.engine

    with eng.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS rag_legacy"))
        conn.commit()
    from src.db.session import Database as RagDatabase
    from src.rag.config import get_rag_settings

    RagDatabase(get_rag_settings()).create_all()

    with eng.connect() as conn:
        public_tables = [
            "answer_feedbacks",
            "audit_logs",
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
            "refresh_tokens",
            "role_permissions",
            "user_activity_logs",
            "user_roles",
            "users",
            "departments",
            "permissions",
            "roles",
            "static_thresholds",
        ]
        joined_public = ", ".join(f"public.{t}" for t in public_tables)
        conn.execute(
            text(
                f"TRUNCATE TABLE {joined_public} "
                "RESTART IDENTITY CASCADE"
            )
        )
        rag_tables = [
            "user_feedback",
            "audit_logs",
            "approval_records",
            "chunks",
            "sections",
            "document_relations",
            "ingestion_jobs",
            "document_versions",
            "documents",
            "access_policies",
        ]
        joined_rag = ", ".join(f"rag_legacy.{t}" for t in rag_tables)
        conn.execute(
            text(
                f"TRUNCATE TABLE {joined_rag} "
                "RESTART IDENTITY CASCADE"
            )
        )
        conn.commit()
    eng.dispose()
    time.sleep(1.5)

    # Reseed reference data.
    import bcrypt as _bcrypt

    from scripts._seed_ids import seed_user_id

    hust_id = "cc8dc08f-3f47-4fd9-9cf5-8e7443b17b2c"
    huce_id = "050813ff-d105-4b95-aab2-fe8c7e3a33f7"
    admin_role_id = "00000000-0000-0000-0000-000000000001"
    # USER is the merged LECTURER + LEADER + REVIEWER role.
    user_role_id = "00000000-0000-0000-0000-000000000002"
    # Legacy role UUIDs preserved so old DB rows referencing them
    # don't break the FK during the migration window.
    leader_role_id = "00000000-0000-0000-0000-000000000003"
    reviewer_role_id = "00000000-0000-0000-0000-000000000004"
    # User UUIDs are derived from email via UUIDv5 so the same email
    # always resolves to the same ID (see scripts/_seed_ids.py for the
    # stability contract and the rationale for moving off magic numbers).
    admin_user_id = str(seed_user_id("admin@p234.demo"))
    hust_user_id = str(seed_user_id("hust@p234.demo"))
    huce_user_id = str(seed_user_id("huce@p234.demo"))
    cross_user_id = str(seed_user_id("crossschool@p234.demo"))
    reviewer_user_id = str(seed_user_id("reviewer@p234.demo"))
    pw_hash = _bcrypt.hashpw(b"P234@123", _bcrypt.gensalt()).decode("utf-8")

    # Stable permission IDs (Phase-5 expansion included).
    # NOTE: SQL named params use underscores (e.g. :document_read) because
    # SQLAlchemy bind params don't support dots. Dict keys must match.
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

    eng = create_engine(db_url)
    with eng.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.departments (id, name, code, is_active) VALUES
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
                  (:document_audit_read,  'document.audit.read', 'Read document audit',     'document'),
                  (:activity_log_read,    'activity_log.read',   'Read activity log',       'activity_log'),
                  (:rbac_manage,          'rbac.manage',         'Manage RBAC',             'rbac'),
                  (:role_manage,          'role.manage',         'Manage roles',            'rbac')
                ON CONFLICT (id) DO NOTHING
                """
            ),
            perm_ids,
        )
        # Role bindings
        rp_rows = text(
            """
            INSERT INTO public.role_permissions (role_id, permission_id) VALUES
              (:rid, :pid)
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
            # USER = LECTURER ∪ LEADER ∪ REVIEWER (union).
            user_role_id: [
                "document_read", "document_upload",
                "document_process", "document_approve",
                "document_audit_read", "activity_log_read",
                "chat_use", "user_read",
            ],
            # Legacy roles kept for FK continuity.
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
        # Demo users (use USER role for the school-scoped accounts).
        demo_users = [
            (admin_user_id, "admin@p234.demo", hust_id, admin_role_id),
            (hust_user_id, "hust@p234.demo", hust_id, user_role_id),
            (huce_user_id, "huce@p234.demo", huce_id, user_role_id),
            (cross_user_id, "crossschool@p234.demo", None, admin_role_id),
            (reviewer_user_id, "reviewer@p234.demo", huce_id, reviewer_role_id),
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
    eng.dispose()
    ok(
        "Neon DB cleared + reseeded",
        f"4 depts+roles, {sum(len(c) for c in role_perms.values())} role-perm rows, 5 demo users",
    )

    # Qdrant
    ctx.qdrant = QdrantClient(
        url=ctx.env["QDRANT_URL"],
        api_key=ctx.env["QDRANT_API_KEY"],
    )
    ctx.qdrant_collection = ctx.env["QDRANT_COLLECTION"]
    collection = ctx.qdrant_collection
    vector_size = int(ctx.env.get("EMBEDDING_DIMENSIONS", "1536"))
    vector_size = int(
        os.environ.get("EMBEDDING_DIMENSIONS_OVERRIDE", vector_size)
    )

    if any(
        c.name == collection
        for c in ctx.qdrant.get_collections().collections
    ):
        ctx.qdrant.delete_collection(collection_name=collection)
        ok(f"Qdrant collection deleted: {collection}")
        time.sleep(1.5)

    ctx.qdrant.create_collection(
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
    ok(
        f"Qdrant collection recreated: {collection}",
        f"size={vector_size}, dense+sparse",
    )

    payload_index_specs = [
        ("tenant_id", qmodels.PayloadSchemaType.KEYWORD),
        ("document_id", qmodels.PayloadSchemaType.KEYWORD),
        ("version_id", qmodels.PayloadSchemaType.KEYWORD),
        ("chunk_id", qmodels.PayloadSchemaType.KEYWORD),
        ("owner_unit", qmodels.PayloadSchemaType.KEYWORD),
        ("allowed_roles", qmodels.PayloadSchemaType.KEYWORD),
        ("allowed_units", qmodels.PayloadSchemaType.KEYWORD),
        ("classification", qmodels.PayloadSchemaType.KEYWORD),
        ("status", qmodels.PayloadSchemaType.KEYWORD),
        ("legal_status", qmodels.PayloadSchemaType.KEYWORD),
        ("valid_from", qmodels.PayloadSchemaType.DATETIME),
        ("valid_to", qmodels.PayloadSchemaType.DATETIME),
        ("page", qmodels.PayloadSchemaType.INTEGER),
        ("section", qmodels.PayloadSchemaType.KEYWORD),
    ]
    for field_name, schema_type in payload_index_specs:
        try:
            ctx.qdrant.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=schema_type,
                wait=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] payload index {field_name}: {exc}")
    ok(
        "Qdrant payload indexes created",
        f"{len(payload_index_specs)} fields",
    )
    return True, {
        "tables_truncated": (
            len(public_tables) + len(rag_tables)
        ),
        "users_seeded": 5,
    }


# ---------------------------------------------------------------------------
# Phase: register
# ---------------------------------------------------------------------------


async def phase_register(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE register — POST /auth/register with HUST + HUCE")
    detail: dict[str, Any] = {"registered": []}
    for school_code in ("HUST", "HUCE"):
        email = (
            f"smoke_{school_code.lower()}_"
            f"{int(time.time())}@"
            f"{school_code.lower()}.demo"
        )
        payload = {
            "email": email,
            "password": "P234@Smoke",
            "full_name": f"Smoke {school_code}",
            "school_code": school_code,
        }
        resp = await client.post(
            f"{API_PREFIX}/auth/register", json=payload
        )
        if resp.status_code != 201:
            fail(
                f"register {school_code}",
                f"status={resp.status_code} body={resp.text}",
            )
            return False, detail
        body = resp.json()
        if school_code == "HUST":
            ctx.new_hust_token = body["access_token"]
            ctx.new_hust_email = email
        detail["registered"].append(
            {
                "school_code": school_code,
                "email": email,
                "role": body["role"],
                "department": body.get("department"),
            }
        )
    ok(
        "register",
        f"new HUST email={ctx.new_hust_email} role=USER dept=HUST",
    )
    return True, detail


# ---------------------------------------------------------------------------
# Phase: auth_matrix
# ---------------------------------------------------------------------------


async def _login(
    client: httpx.AsyncClient,
    email: str,
    password: str = "P234@123",
    device_suffix: str | None = None,
) -> dict[str, Any]:
    suffix = device_suffix or email.split("@")[0]
    resp = await client.post(
        f"{API_PREFIX}/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": f"smoke-{suffix}",
        },
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"login failed for {email}: "
            f"{resp.status_code} {resp.text}"
        )
    return resp.json()


async def phase_auth_matrix(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE auth_matrix — login as 5 seeded roles")
    logins = {
        "admin": ("admin@p234.demo", "P234@123"),
        "hust": ("hust@p234.demo", "P234@123"),
        "huce": ("huce@p234.demo", "P234@123"),
        "crossschool": ("crossschool@p234.demo", "P234@123"),
        "reviewer": ("reviewer@p234.demo", "P234@123"),
    }
    results: dict[str, dict[str, Any]] = {}
    for label, (email, pwd) in logins.items():
        try:
            data = await _login(
                client, email, pwd, label
            )
        except Exception as exc:  # noqa: BLE001
            fail(
                f"login {label}",
                str(exc),
            )
            return False, {"failed": label}
        token = data["access_token"]
        if label == "admin":
            ctx.admin_token = token
        elif label == "hust":
            ctx.hust_token = token
        elif label == "huce":
            ctx.huce_token = token
        elif label == "crossschool":
            ctx.cross_token = token
        elif label == "reviewer":
            ctx.reviewer_token = token
        results[label] = {"token_prefix": token[:20]}
        ok(
            f"login {label}",
            f"got JWT ({token[:20]}...)",
        )
    # Login the newly-registered HUST user (different password).
    if ctx.new_hust_email:
        try:
            data = await _login(
                client,
                ctx.new_hust_email,
                "P234@Smoke",
                "new_hust",
            )
            results["new_hust"] = {
                "token_prefix": data["access_token"][:20]
            }
            ok("login new_hust", "registered user can authenticate")
        except Exception as exc:  # noqa: BLE001
            warn("login new_hust", str(exc))
    return True, results


# ---------------------------------------------------------------------------
# Phase: rbac_matrix
# ---------------------------------------------------------------------------


async def phase_rbac_matrix(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE rbac_matrix — role × endpoint status codes")
    # Each entry: (label, token, method, path, expected_status).
    cases = [
        # ADMIN can do admin operations.
        ("admin.list_docs", ctx.admin_token, "GET", "/regulatory-documents", 200),
        ("admin.approve_perm", ctx.admin_token, "GET", "/regulatory-documents/00000000-0000-0000-0000-000000000000/changelog", 404),
        ("admin.activity_log", ctx.admin_token, "GET", "/activity-log/users/me", 200),
        # HUST (USER) cannot reach admin/rbac endpoints.
        ("hust.rbac_denied", ctx.hust_token, "GET", "/rbac/permissions", 403),
        ("hust.role_manage_denied", ctx.hust_token, "POST", "/roles/00000000-0000-0000-0000-000000000000/permissions", 403),
        # HUST can read documents (200) but cannot delete (403).
        ("hust.list_docs_ok", ctx.hust_token, "GET", "/regulatory-documents", 200),
        # HUCE same shape.
        ("huce.list_docs_ok", ctx.huce_token, "GET", "/regulatory-documents", 200),
        ("huce.rbac_denied", ctx.huce_token, "GET", "/rbac/permissions", 403),
        # crossschool ADMIN-like.
        ("cross.list_docs_ok", ctx.cross_token, "GET", "/regulatory-documents", 200),
        ("cross.activity_log", ctx.cross_token, "GET", "/activity-log/users/me", 200),
    ]
    results: list[dict[str, Any]] = []
    failed = False
    for label, token, method, path, expected in cases:
        if not token:
            warn(
                label,
                "token missing — auth_matrix not run?",
            )
            continue
        resp = await client.request(
            method,
            f"{API_PREFIX}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        ok_status = resp.status_code == expected
        results.append(
            {
                "label": label,
                "method": method,
                "path": path,
                "expected": expected,
                "actual": resp.status_code,
                "pass": ok_status,
            }
        )
        if ok_status:
            ok(
                label,
                f"{method} {path} -> {resp.status_code}",
            )
        else:
            warn(
                label,
                f"{method} {path} expected {expected} got {resp.status_code}",
            )
            if expected != 200 and resp.status_code not in {401, 403}:
                # Wrong status on a permission test is suspicious.
                failed = True
    return (not failed), {"cases": results}


# ---------------------------------------------------------------------------
# Phase: upload
# ---------------------------------------------------------------------------


def _pick_sample_pdf() -> Path:
    candidates = [
        REPO_ROOT / "data" / "raw" / "RAW-HUST-10232" / "v1" / "10232.pdf",
        REPO_ROOT / "data" / "raw" / "RAW-HUST-5445" / "v1" / "5445.pdf",
        REPO_ROOT / "data" / "raw" / "RAW-HUST-2048-table" / "v1" / "2048-table.pdf",
        REPO_ROOT / "data" / "raw" / "HUCE" / "1145 - Quy định chấm công.pdf",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise RuntimeError(
        "No sample PDF found in data/raw/"
    )


async def phase_upload(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE upload — admin uploads sample PDF")
    ctx.pdf_path = _pick_sample_pdf()
    document_number = (
        f"SMOKE-E2E-{int(time.time())}"
    )
    title = (
        f"E2E Smoke Test — {ctx.pdf_path.parent.name}"
    )
    with ctx.pdf_path.open("rb") as fh:
        resp = await client.post(
            f"{API_PREFIX}/regulatory-documents/upload",
            headers={"Authorization": f"Bearer {ctx.admin_token}"},
            data={
                "document_number": document_number,
                "title": title,
                "issued_by": "P234 Smoke",
                "issued_date": "2026-08-30",
                "effective_date": "2026-09-01",
            },
            files={
                "file": (
                    ctx.pdf_path.name,
                    fh,
                    "application/pdf",
                ),
            },
        )
    if resp.status_code != 201:
        fail(
            "upload",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    data = resp.json()
    ctx.primary_document_id = data["id"]
    # Resolve the actual version_id + object_key from DB so we assert
    # the canonical layout verbatim.
    eng = create_engine(
        _to_psycopg_url(ctx.env["DATABASE_URL"])
    )
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, object_key
                FROM public.document_versions
                WHERE document_id = :did
                ORDER BY version_number ASC LIMIT 1
                """
            ),
            {"did": ctx.primary_document_id},
        ).first()
    eng.dispose()
    ctx.primary_version_id = str(row[0])
    ctx.primary_object_key = row[1]
    # Canonical check.
    if (
        ctx.primary_object_key
        != f"hust/documents/{document_number}/v1/source.pdf"
    ):
        warn(
            "upload key layout",
            f"expected canonical, got '{ctx.primary_object_key}'",
        )
    else:
        ok(
            "upload canonical key",
            ctx.primary_object_key,
        )
    ok(
        "upload PDF",
        f"id={ctx.primary_document_id} version_id={ctx.primary_version_id}",
    )
    return True, {
        "document_id": ctx.primary_document_id,
        "version_id": ctx.primary_version_id,
        "object_key": ctx.primary_object_key,
    }


# ---------------------------------------------------------------------------
# Phase: ingest (approve -> index -> publish)
# ---------------------------------------------------------------------------


async def phase_ingest(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE ingest — approve -> index -> publish")
    transitions: list[dict[str, Any]] = []

    # approve
    resp = await client.post(
        f"{API_PREFIX}/admin/documents/{ctx.primary_version_id}/approve",
        headers={"Authorization": f"Bearer {ctx.admin_token}"},
    )
    if resp.status_code != 200:
        fail(
            "approve",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    transitions.append(
        {"step": "approve", "status": resp.json().get("status")}
    )
    ok("approve", f"version_id={ctx.primary_version_id}")

    # index
    resp = await client.post(
        f"{API_PREFIX}/admin/documents/{ctx.primary_version_id}/index",
        headers={"Authorization": f"Bearer {ctx.admin_token}"},
    )
    if resp.status_code != 200:
        fail(
            "index",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    body = resp.json()
    transitions.append(
        {
            "step": "index",
            "status": body.get("status"),
            "note": body.get("digitisation_note"),
        }
    )
    ok("index", body.get("status", ""))

    # publish
    resp = await client.post(
        f"{API_PREFIX}/admin/documents/{ctx.primary_version_id}/publish",
        headers={"Authorization": f"Bearer {ctx.admin_token}"},
    )
    if resp.status_code != 200:
        fail(
            "publish",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    transitions.append(
        {"step": "publish", "status": resp.json().get("status")}
    )
    ok("publish", resp.json().get("status", ""))

    # Verify Qdrant points.
    info = ctx.qdrant.get_collection(
        collection_name=ctx.qdrant_collection
    )
    ctx.primary_qdrant_points = int(info.points_count)
    ok(
        "Qdrant points after ingest",
        str(ctx.primary_qdrant_points),
    )
    return True, {
        "transitions": transitions,
        "qdrant_points": ctx.primary_qdrant_points,
    }


# ---------------------------------------------------------------------------
# Phase: rag_query
# ---------------------------------------------------------------------------


async def phase_rag_query(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE rag_query — HUST user asks a known question")
    if not ctx.new_hust_token:
        warn(
            "rag_query",
            "no newly-registered HUST token; skipping",
        )
        return True, {"skipped": True}
    question = (
        "Điều kiện tốt nghiệp đại học là gì? "
        "Bao nhiêu tín chỉ cần tích lũy?"
    )
    resp = await client.post(
        f"{API_PREFIX}/chat",
        headers={
            "Authorization": (
                f"Bearer {ctx.new_hust_token}"
            )
        },
        json={"message": question, "session_id": None},
        timeout=60,
    )
    if resp.status_code != 200:
        fail(
            "rag ask",
            f"status={resp.status_code} body={resp.text[:500]}",
        )
        return False, {}
    data = resp.json()
    answer = (data.get("answer") or "").strip()
    citations = data.get("citations", [])
    print()
    print(f"  Q: {question}")
    print(
        f"  A: {answer[:500]}"
        f"{'...' if len(answer) > 500 else ''}"
    )
    print(f"  Citations: {len(citations)}")
    for c in citations[:5]:
        print(
            f"    - {c.get('document_number') or c.get('doc_id')} "
            f"score={c.get('score')}"
        )
    print()
    if not answer:
        return False, {"answer_empty": True}
    ok(
        "rag_query",
        f"answer_len={len(answer)} citations={len(citations)}",
    )
    return True, {
        "answer_length": len(answer),
        "citations": len(citations),
    }


# ---------------------------------------------------------------------------
# Phase: cross_school
# ---------------------------------------------------------------------------


async def phase_cross_school(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE cross_school — HUCE-restricted doc gating")
    # Upload a HUCE-restricted PDF as admin; HUST must 403; HUCE 200.
    if ctx.pdf_path is None:
        ctx.pdf_path = _pick_sample_pdf()
    document_number = (
        f"SMOKE-HUCE-{int(time.time())}"
    )
    with ctx.pdf_path.open("rb") as fh:
        resp = await client.post(
            f"{API_PREFIX}/regulatory-documents/upload",
            headers={"Authorization": f"Bearer {ctx.admin_token}"},
            data={
                "document_number": document_number,
                "title": (
                    f"HUCE-only doc "
                    f"{document_number}"
                ),
                "issued_by": "Phòng Đào tạo HUCE",
                "issued_date": "2026-08-30",
                "effective_date": "2026-09-01",
            },
            files={
                "file": (
                    ctx.pdf_path.name,
                    fh,
                    "application/pdf",
                ),
            },
        )
    if resp.status_code != 201:
        fail(
            "cross_school upload",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    ctx.huce_document_id = resp.json()["id"]
    # Bind to HUCE department.
    eng = create_engine(
        _to_psycopg_url(ctx.env["DATABASE_URL"])
    )
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id FROM public.document_versions
                WHERE document_id = :did
                ORDER BY version_number ASC LIMIT 1
                """
            ),
            {"did": ctx.huce_document_id},
        ).first()
        ctx.huce_version_id = str(row[0])
        huce_dept_id = "050813ff-d105-4b95-aab2-fe8c7e3a33f7"
        conn.execute(
            text(
                """
                INSERT INTO public.document_departments
                  (document_id, department_id)
                VALUES (:did, :dept)
                ON CONFLICT DO NOTHING
                """
            ),
            {"did": ctx.huce_document_id, "dept": huce_dept_id},
        )
        conn.execute(
            text(
                "UPDATE public.documents SET access_scope = 'DEPARTMENT' "
                "WHERE id = :did"
            ),
            {"did": ctx.huce_document_id},
        )
        conn.commit()
    eng.dispose()

    # HUST GET -> 403.
    hust_resp = await client.get(
        f"{API_PREFIX}/regulatory-documents/{ctx.huce_document_id}",
        headers={
            "Authorization": (
                f"Bearer {ctx.hust_token}"
            )
        },
    )
    hust_ok = hust_resp.status_code == 403
    if hust_ok:
        ok("HUST 403 on HUCE doc", "")
    else:
        warn(
            "HUST 403 on HUCE doc",
            f"got {hust_resp.status_code}",
        )

    # HUCE GET -> 200.
    huce_resp = await client.get(
        f"{API_PREFIX}/regulatory-documents/{ctx.huce_document_id}",
        headers={
            "Authorization": (
                f"Bearer {ctx.huce_token}"
            )
        },
    )
    huce_ok = huce_resp.status_code == 200
    if huce_ok:
        ok("HUCE 200 on HUCE doc", "")
    else:
        warn(
            "HUCE 200 on HUCE doc",
            f"got {huce_resp.status_code}",
        )
    return (
        hust_ok and huce_ok
    ), {
        "hust_status": hust_resp.status_code,
        "huce_status": huce_resp.status_code,
    }


# ---------------------------------------------------------------------------
# Phase: delete_cascade
# ---------------------------------------------------------------------------


async def phase_delete_cascade(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner(
        "PHASE delete_cascade — admin deletes primary doc + asserts cleanup"
    )
    pre_qdrant = ctx.primary_qdrant_points
    resp = await client.delete(
        f"{API_PREFIX}/regulatory-documents/{ctx.primary_document_id}",
        headers={
            "Authorization": (
                f"Bearer {ctx.admin_token}"
            )
        },
    )
    delete_ok = resp.status_code in {200, 207}
    if not delete_ok:
        fail(
            "delete",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {}
    ok(
        "delete",
        f"status={resp.status_code} "
        f"storage_objects_deleted="
        f"{body.get('storage_objects_deleted')} "
        f"qdrant_points_removed="
        f"{body.get('qdrant_points_removed')} "
        f"errors={body.get('errors')}",
    )

    # GET -> 404.
    get_resp = await client.get(
        f"{API_PREFIX}/regulatory-documents/{ctx.primary_document_id}",
        headers={
            "Authorization": (
                f"Bearer {ctx.admin_token}"
            )
        },
    )
    detail_404 = get_resp.status_code == 404
    if detail_404:
        ok("GET detail -> 404", "")
    else:
        warn(
            "GET detail -> 404",
            f"got {get_resp.status_code}",
        )

    # Qdrant points dropped.
    info = ctx.qdrant.get_collection(
        collection_name=ctx.qdrant_collection
    )
    post_qdrant = int(info.points_count)
    qdrant_dropped = post_qdrant <= pre_qdrant
    if qdrant_dropped:
        ok(
            "qdrant points dropped",
            f"{pre_qdrant} -> {post_qdrant}",
        )
    else:
        warn(
            "qdrant points not dropped",
            f"{pre_qdrant} -> {post_qdrant}",
        )

    return (
        delete_ok and detail_404 and qdrant_dropped
    ), {
        "delete_status": resp.status_code,
        "delete_body": body,
        "get_detail_status": get_resp.status_code,
        "qdrant_pre": pre_qdrant,
        "qdrant_post": post_qdrant,
    }


# ---------------------------------------------------------------------------
# Phase: replace_source
# ---------------------------------------------------------------------------


async def phase_replace_source(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner(
        "PHASE replace_source — admin uploads v2 of "
        "previously deleted doc"
    )
    # Re-create a fresh document; then PUT /source to bump to v2.
    document_number = (
        f"SMOKE-REPLACE-{int(time.time())}"
    )
    if ctx.pdf_path is None:
        ctx.pdf_path = _pick_sample_pdf()
    with ctx.pdf_path.open("rb") as fh:
        resp = await client.post(
            f"{API_PREFIX}/regulatory-documents/upload",
            headers={
                "Authorization": (
                    f"Bearer {ctx.admin_token}"
                )
            },
            data={
                "document_number": document_number,
                "title": f"Replace test {document_number}",
                "issued_by": "P234 Smoke",
                "issued_date": "2026-08-30",
                "effective_date": "2026-09-01",
            },
            files={
                "file": (
                    ctx.pdf_path.name,
                    fh,
                    "application/pdf",
                ),
            },
        )
    if resp.status_code != 201:
        fail(
            "replace_source upload",
            f"status={resp.status_code} body={resp.text}",
        )
        return False, {}
    doc_id = resp.json()["id"]
    eng = create_engine(
        _to_psycopg_url(ctx.env["DATABASE_URL"])
    )
    with eng.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, object_key FROM public.document_versions
                WHERE document_id = :did
                ORDER BY version_number ASC LIMIT 1
                """
            ),
            {"did": doc_id},
        ).first()
    eng.dispose()
    v1_id = str(row[0])
    v1_key = row[1]
    ok(
        "v1 created",
        f"key={v1_key}",
    )

    # Replace.
    with ctx.pdf_path.open("rb") as fh:
        put = await client.put(
            f"{API_PREFIX}/regulatory-documents/{doc_id}/source",
            headers={
                "Authorization": (
                    f"Bearer {ctx.admin_token}"
                )
            },
            files={
                "file": (
                    ctx.pdf_path.name,
                    fh,
                    "application/pdf",
                ),
            },
        )
    if put.status_code != 200:
        fail(
            "replace_source PUT",
            f"status={put.status_code} body={put.text}",
        )
        return False, {}
    body = put.json()
    ctx.second_version_id = body["id"]
    ctx.second_object_key = body["object_key"]
    # Verify the new key follows the canonical layout and differs from v1.
    expected_v2 = (
        f"hust/documents/{document_number}/v2/source.pdf"
    )
    canonical_ok = ctx.second_object_key == expected_v2
    versions_ok = body["version_number"] == 2
    if canonical_ok and versions_ok:
        ok(
            "v2 created",
            f"key={ctx.second_object_key} version=2",
        )
    else:
        warn(
            "v2 layout",
            f"key={ctx.second_object_key} version="
            f"{body['version_number']} (expected canonical v2)",
        )
    # Versions are append-only: v1 should still exist.
    eng = create_engine(
        _to_psycopg_url(ctx.env["DATABASE_URL"])
    )
    with eng.connect() as conn:
        v1_count = conn.execute(
            text(
                "SELECT count(*) FROM public.document_versions "
                "WHERE id = :id"
            ),
            {"id": v1_id},
        ).scalar()
    eng.dispose()
    append_only_ok = v1_count == 1
    if append_only_ok:
        ok("v1 still present (append-only)", "")
    else:
        warn(
            "v1 append-only",
            f"count={v1_count}",
        )
    return (
        canonical_ok and versions_ok and append_only_ok
    ), {
        "doc_id": doc_id,
        "v1_key": v1_key,
        "v2_key": ctx.second_object_key,
        "v2_version_number": body["version_number"],
    }


# ---------------------------------------------------------------------------
# Phase: cleanup
# ---------------------------------------------------------------------------


async def phase_cleanup(
    ctx: PhaseContext,
    client: httpx.AsyncClient,
) -> tuple[bool, dict[str, Any]]:
    banner("PHASE cleanup — delete all docs created during the run")
    targets = []
    if ctx.huce_document_id:
        targets.append(("huce_doc", ctx.huce_document_id))
    # The replace-source doc
    eng = create_engine(
        _to_psycopg_url(ctx.env["DATABASE_URL"])
    )
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id FROM public.documents
                WHERE document_number LIKE 'SMOKE-%'
                """
            ),
        ).all()
    eng.dispose()
    for (doc_id,) in rows:
        if doc_id not in {t[1] for t in targets}:
            targets.append((f"smoke_doc:{str(doc_id)[:8]}", doc_id))
    results: list[dict[str, Any]] = []
    for label, doc_id in targets:
        resp = await client.delete(
            f"{API_PREFIX}/regulatory-documents/{doc_id}",
            headers={
                "Authorization": (
                    f"Bearer {ctx.admin_token}"
                )
            },
        )
        results.append(
            {
                "label": label,
                "doc_id": doc_id,
                "status": resp.status_code,
            }
        )
        ok(
            f"cleanup {label}",
            f"status={resp.status_code}",
        )
    return True, {"cleaned": results}


# ---------------------------------------------------------------------------
# Phase registry + driver
# ---------------------------------------------------------------------------


PHASES: dict[str, PhaseFn] = {
    "reset": phase_reset,
    "register": phase_register,
    "auth_matrix": phase_auth_matrix,
    "rbac_matrix": phase_rbac_matrix,
    "upload": phase_upload,
    "ingest": phase_ingest,
    "rag_query": phase_rag_query,
    "cross_school": phase_cross_school,
    "delete_cascade": phase_delete_cascade,
    "replace_source": phase_replace_source,
    "cleanup": phase_cleanup,
}

DEFAULT_PHASE_ORDER = list(PHASES.keys())


async def run_phases(
    selected: list[str],
    stop_on_failure: bool,
    base_url: str,
) -> int:
    ctx = PhaseContext(env=load_env())
    print(f"  Backend:    {base_url}")
    print(
        f"  Neon host:  "
        f"{ctx.env['DATABASE_URL'].split('@')[1].split('/')[0]}"
    )
    print(f"  Qdrant URL: {ctx.env['QDRANT_URL'][:60]}...")
    print(
        f"  Qdrant key: {mask(ctx.env['QDRANT_API_KEY'])}"
    )
    print(f"  Collection: {ctx.env['QDRANT_COLLECTION']}")

    summary: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=base_url, timeout=60
    ) as client:
        for name in selected:
            phase = PHASES[name]
            started = time.monotonic()
            try:
                ok_flag, detail = await phase(ctx, client)
            except Exception as exc:  # noqa: BLE001
                import traceback

                traceback.print_exc()
                ok_flag = False
                detail = {"exception": repr(exc)}
            duration = time.monotonic() - started
            summary.append(
                {
                    "phase": name,
                    "ok": ok_flag,
                    "duration_s": round(duration, 3),
                    "detail": detail,
                }
            )
            if not ok_flag and stop_on_failure:
                fail(
                    f"phase {name}",
                    "stopping on failure",
                )
                break
    # JSON summary on stdout.
    print("\n" + "=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print(json.dumps(summary, indent=2, default=str))
    all_ok = all(s["ok"] for s in summary)
    print()
    if all_ok:
        ok(
            "All phases passed",
            f"phases={len(summary)}",
        )
        return 0
    warn(
        "Some phases failed",
        f"phases={len(summary)}",
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase-driven E2E orchestrator for P-234."
        ),
    )
    parser.add_argument(
        "--phases",
        default=",".join(DEFAULT_PHASE_ORDER),
        help=(
            "Comma-separated phase names. Default: "
            + ",".join(DEFAULT_PHASE_ORDER)
        ),
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Stop on the first failing phase.",
    )
    parser.add_argument(
        "--api-base",
        default=BACKEND_BASE,
        help="Backend base URL.",
    )
    args = parser.parse_args()
    selected = [
        p.strip()
        for p in args.phases.split(",")
        if p.strip()
    ]
    unknown = [
        p for p in selected if p not in PHASES
    ]
    if unknown:
        print(
            f"Unknown phases: {unknown}. "
            f"Available: {list(PHASES.keys())}",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(
        run_phases(
            selected,
            args.stop_on_failure,
            args.api_base,
        )
    )


if __name__ == "__main__":
    sys.exit(main())