import asyncio
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from config import get_settings
from persistence.tenant.database import metadata

# Import ORM models để chúng đăng ký vào metadata.
from persistence.tenant.models.permission import PermissionModel
from persistence.tenant.models.refresh_token import RefreshTokenModel
from persistence.tenant.models.role import RoleModel
from persistence.tenant.models.role_permission import RolePermissionModel
from persistence.tenant.models.user import UserModel
from persistence.tenant.models.user_role import UserRoleModel

import persistence.tenant.models.document
import persistence.tenant.models.document_version
import persistence.tenant.models.document_relation
import persistence.tenant.models.document_effectiveness_alert
import persistence.tenant.models.document_application_scope
import persistence.tenant.models.chat_session
import persistence.tenant.models.chat_turn
import persistence.tenant.models.answer_feedback

# Import Table configurations để audit tables
# cũng được đăng ký vào cùng metadata.
from persistence.tenant.configurations.audit_log_configuration import (
    audit_logs,
)
from persistence.tenant.configurations.audit_outbox_configuration import (
    audit_outbox,
)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


def _alembic_url(url: str) -> str:
    """Convert ``postgresql://`` to ``postgresql+psycopg://`` so SQLAlchemy
    uses psycopg v3 (the only driver installed in the conda p234 env).
    """
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    _alembic_url(settings.database_url),
)

target_metadata = metadata


def run_migrations_offline() -> None:
    url = config.get_main_option(
        "sqlalchemy.url"
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            do_run_migrations
        )

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(
        run_async_migrations()
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()