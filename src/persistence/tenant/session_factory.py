from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class TenantSessionFactory:
    def __init__(self) -> None:
        self._engines: dict[
            str,
            AsyncEngine,
        ] = {}

        self._session_factories: dict[
            str,
            async_sessionmaker[AsyncSession],
        ] = {}

    @staticmethod
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

    def get_session_factory(
        self,
        database_url: str,
    ) -> async_sessionmaker[
        AsyncSession
    ]:
        normalized_url = (
            self._normalize_database_url(
                database_url
            )
        )

        session_factory = (
            self._session_factories.get(
                normalized_url
            )
        )

        if session_factory is None:
            from sqlalchemy import event

            engine = create_async_engine(
                normalized_url,
                pool_pre_ping=True,
            )

            # All tenant models use the ``public`` schema (Postgres) or
            # no schema (SQLite). Default the search_path to ``public``
            # so unqualified table references resolve to ``public.*``.
            if normalized_url.startswith(
                (
                    "postgresql://",
                    "postgres://",
                    "postgresql+psycopg://",
                )
            ):
                @event.listens_for(
                    engine.sync_engine, "connect"
                )
                def _set_search_path(
                    dbapi_conn,
                    _record,
                ):  # noqa: ANN001
                    cursor = dbapi_conn.cursor()
                    try:
                        cursor.execute(
                            "SET search_path TO public"
                        )
                        dbapi_conn.commit()
                    finally:
                        cursor.close()

            session_factory = (
                async_sessionmaker(
                    bind=engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
            )

            self._engines[
                normalized_url
            ] = engine

            self._session_factories[
                normalized_url
            ] = session_factory

        return session_factory

    def create(
        self,
        database_url: str,
    ) -> AsyncSession:
        session_factory = (
            self.get_session_factory(
                database_url
            )
        )

        return session_factory()

    async def dispose(
        self,
    ) -> None:
        for engine in (
            self._engines.values()
        ):
            await engine.dispose()

        self._engines.clear()

        self._session_factories.clear()
