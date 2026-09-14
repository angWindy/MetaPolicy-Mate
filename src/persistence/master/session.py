from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings


settings = get_settings()


def _normalize_database_url(
    database_url: str,
) -> str:
    if database_url.startswith(
        "postgresql://"
    ):
        return database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    if database_url.startswith(
        "postgres://"
    ):
        return database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    if database_url.startswith(
        "sqlite://"
    ):
        return database_url.replace(
            "sqlite://",
            "sqlite+aiosqlite://",
            1,
        )

    return database_url


master_engine = create_async_engine(
    _normalize_database_url(
        settings.master_database_url
    ),
    pool_pre_ping=True,
)


master_session_factory = async_sessionmaker(
    bind=master_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_master_session(
) -> AsyncIterator[AsyncSession]:
    async with master_session_factory() as session:
        yield session