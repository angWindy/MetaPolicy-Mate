"""Validate that SQLite is rejected as a runtime database.

SQLite remains supported only for the unit test suite via APP_ENV=test.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.rag.config import RAGSettings


def test_sqlite_url_rejected_for_development():
    with pytest.raises(ValidationError) as exc:
        RAGSettings(
            app_env="development",
            database_url="sqlite:///./data/app.db",
        )
    assert "SQLite is no longer supported" in str(exc.value)


def test_sqlite_url_rejected_for_production():
    with pytest.raises(ValidationError) as exc:
        RAGSettings(
            app_env="production",
            database_url="sqlite:///:memory:",
        )
    assert "SQLite is no longer supported" in str(exc.value)


def test_postgres_url_accepted():
    settings = RAGSettings(
        app_env="development",
        database_url="postgresql+psycopg://p234:p234@localhost:5432/p234",
    )
    assert settings.database_url.startswith("postgresql")


def test_sqlite_url_allowed_for_test_env():
    # In-memory SQLite is the unit suite fixture; do not regress this path.
    settings = RAGSettings(
        app_env="test",
        database_url="sqlite:///:memory:",
    )
    assert settings.database_url == "sqlite:///:memory:"


def test_unknown_scheme_rejected():
    with pytest.raises(ValidationError) as exc:
        RAGSettings(
            app_env="development",
            database_url="mysql://user:pass@localhost:3306/db",
        )
    assert "Unsupported DATABASE_URL scheme" in str(exc.value)
