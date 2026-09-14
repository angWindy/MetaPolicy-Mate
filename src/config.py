"""Application settings for the FastAPI backend.

Single source of truth for backend configuration. The RAG and database
module has its own ``RAGSettings`` (see ``src/rag/config.py``) and shares
the same ``DATABASE_URL`` environment variable so the two layers always
point at the same Postgres cluster (backend uses the ``public`` schema,
RAG uses the ``rag_legacy`` schema). See ``scripts/check_env_consistency.py``
for a runtime sanity check.

Tenant identity is **per-user**, sourced from each user's bound
``department_id`` / ``department.code`` via the JWT token. There is no
global ``TENANT_ID`` / ``TENANT_CODE`` constant — the demo is single-instance
but multi-tenant-by-data, and the authoritative tenant identity lives on
the user row (from the ``department`` FK), not in environment defaults.
Role/permission is resolved from the ``school_code`` collected on the
registration form (RBAC identity), independent of any settings constants.

The legacy ``school_id`` / ``school_code`` Settings fields default to
``None`` so any remaining code path that reads them raises loudly —
the fix is to derive tenant identity from ``user.department_id`` /
``department.code`` instead (as login/refresh/register handlers already do).
"""

from functools import lru_cache
from typing import Literal
from uuid import UUID

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"

    app_env: Literal[
        "development",
        "production",
        "test",
    ] = "development"

    app_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
    )

    app_host: str = "0.0.0.0"

    log_level: Literal[
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
    ] = "INFO"

    cors_origins: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://host.docker.internal:3000"
    )

    # LLM
    openai_api_key: str = ""

    model_name: str = "gpt-4o-mini"

    llm_temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
    )

    # Database — single shared key with RAG module (src/rag/config.py).
    # Backend uses schema ``public``; RAG uses schema ``rag_legacy``.
    # ``schema_translate_map`` is applied in src/db/session.py.
    database_url: str

    redis_url: str = (
        "redis://localhost:6379/0"
    )

    # Cloudflare R2
    r2_endpoint: str

    r2_access_key_id: str

    r2_secret_access_key: str

    r2_bucket_name: str

    # Future SaaS Master (unused in the single-tenant demo).
    master_database_url: (
        str | None
    ) = None

    # Vector Store
    chroma_persist_dir: str = (
        "./data/chroma"
    )

    # Auth
    jwt_issuer: str

    jwt_audience: str

    jwt_secret_key: str

    jwt_access_token_minutes: int = 30

    jwt_refresh_token_days: int = 7

    # BE -> AI compatibility policy.
    #
    # Default classification of the current authenticated user when the
    # adapter has to build a UserContext for the legacy AI pipeline.
    # This is NOT a tenant configuration.
    rag_default_clearance: Literal[
        "public",
        "internal",
        "confidential",
        "restricted",
    ] = "internal"


    chat_rate_limit_requests: int = Field(
        default=1000,
        ge=1,
        le=10000,
    )

    chat_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=86400,
    )

    # ─── Tenant identity — DEPRECATED ────────────────────────────────────────
    # These fields used to carry a hardcoded ``aaaaaaaa-bbbb-cccc-dddd-
    # eeeeeeeeeeee`` UUID and a ``P234-DEMO`` code, which propagated to
    # every JWT, every R2 key, every Qdrant payload and looked like a
    # bug. They now default to ``None`` so any code path that still
    # reads them raises loudly — the fix is to derive the per-user
    # tenant from ``user.department_id`` / ``department.code`` instead.
    #
    # Kept on the model only so existing DI registration
    # (``container.register_instance(Settings, settings)``) keeps
    # working; do NOT add new call sites that read these.
    school_id: UUID | None = None
    school_code: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()