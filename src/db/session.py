from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base
from src.rag.config import RAGSettings


class Database:
    """RAG-module database wiring.

    All RAG tables live in the ``public`` Postgres schema (see
    ``src/db/models.py``). The legacy ``rag_legacy`` schema was dropped in
    Phase 4.2 cleanup — every migration target is now in ``public``.
    """

    def __init__(self, settings: RAGSettings):
        kwargs: dict = {"pool_pre_ping": True}
        database_url = settings.database_url
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )
        elif database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )

        scheme = database_url.split("://", 1)[0].lower()
        if scheme.startswith("sqlite"):
            # SQLite is only allowed for the test environment (see
            # RAGSettings.validate_database_url). Production must use Postgres.
            kwargs["connect_args"] = {"check_same_thread": False}
            if database_url in {"sqlite://", "sqlite:///:memory:"}:
                kwargs["poolclass"] = StaticPool
        self.engine = create_engine(database_url, **kwargs)
        if scheme.startswith("postgresql"):
            # Force the search_path to public so unqualified table references
            # resolve correctly even when no schema_translate_map is applied.
            @event.listens_for(self.engine, "connect")
            def _set_search_path(dbapi_conn, _record):  # noqa: ANN001
                cursor = dbapi_conn.cursor()
                try:
                    cursor.execute(
                        "SET search_path TO public"
                    )
                    dbapi_conn.commit()
                finally:
                    cursor.close()
        self.session_factory = sessionmaker(
            bind=self.engine, class_=Session, expire_on_commit=False
        )

    def create_all(self) -> None:
        # Phase 4.2 cleanup: rag_legacy schema was dropped. Production tables
        # live in ``public`` and are owned by Alembic migrations, so we must
        # NOT let SQLAlchemy try to recreate them — its model column types
        # (VARCHAR) collide with the real ``public.*`` schema (UUID PKs).
        # Only honor create_all for SQLite, which is the standalone test
        # backend in RAGSettings.validate_database_url.
        if self.engine.dialect.name == "sqlite":
            Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()
