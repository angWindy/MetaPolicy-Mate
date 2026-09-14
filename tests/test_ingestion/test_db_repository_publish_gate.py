"""Regression tests for the publish gate (strict INDEXED -> PUBLISHED).

A version must be INDEXED (vector in Qdrant) before it can be PUBLISHED.
This prevents the PostgreSQL/RAG drift where the DB says "published"
but the vector store is empty.

There are two gates in the codebase:

1. **Legacy** — ``src.db.repository.Repository.publish_version``
   accepts ``APPROVED`` *or* ``INDEXED``. Per BUGS_FOUND.md B-P3-01
   this module is deprecated and emits ``DeprecationWarning`` on
   import. The legacy tests below document its current (weaker)
   behaviour; once the legacy path is deleted they go away with it.

2. **Production** — ``src.presentation.api.routers.admin_router
   .publish_document_version`` (and the underlying repository
   adapters) enforces the strict ``INDEXED -> PUBLISHED`` transition.
   The regression tests in ``test_admin_publish_gate.py`` assert the
   production gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.db.repository import Repository
from src.domain.schemas import ProcessingStatus


@pytest.fixture
def fake_session() -> MagicMock:
    session = MagicMock()
    session_factory = MagicMock(return_value=session)
    session.__enter__ = lambda self: session
    session.__exit__ = lambda self, *args: None
    return session, session_factory


def test_legacy_publish_accepts_approved_or_indexed(fake_session):
    """Legacy gate (deprecated, B-P3-01) — weaker than production.

    Documents the current legacy behaviour so the next agent doesn't
    "fix" it by silently tightening the gate: the production code
    path is the right place to enforce strict ordering.
    """
    session, session_factory = fake_session
    version = SimpleNamespace(
        id="v1",
        processing_status=ProcessingStatus.APPROVED.value,
        replaces_version_id=None,
        effective_from=None,
        legal_status="draft",
        chunks=[],
    )
    session.get.return_value = version

    repo = Repository(session_factory=session_factory)
    # Legacy gate ALLOWS APPROVED -> PUBLISHED (the weaker behaviour).
    # Production traffic does not hit this path; admin_router enforces
    # the strict gate instead (see test_admin_publish_gate.py).
    result = repo.publish_version("v1")
    assert result.processing_status == ProcessingStatus.PUBLISHED.value
    assert session.commit.called


def test_legacy_publish_blocks_when_status_is_failed(fake_session):
    session, session_factory = fake_session
    version = SimpleNamespace(
        id="v1",
        processing_status=ProcessingStatus.FAILED.value,
        replaces_version_id=None,
        effective_from=None,
        legal_status="draft",
        chunks=[],
    )
    session.get.return_value = version

    repo = Repository(session_factory=session_factory)
    with pytest.raises(ValueError):
        repo.publish_version("v1")


def test_legacy_publish_succeeds_when_indexed(fake_session):
    """Positive path: indexed versions can be published."""
    session, session_factory = fake_session
    version = SimpleNamespace(
        id="v1",
        processing_status=ProcessingStatus.INDEXED.value,
        replaces_version_id=None,
        effective_from=None,
        legal_status="draft",
        chunks=[],
    )
    session.get.return_value = version

    repo = Repository(session_factory=session_factory)
    result = repo.publish_version("v1")
    assert result.processing_status == ProcessingStatus.PUBLISHED.value
    assert session.commit.called


def test_legacy_publish_blocks_when_version_missing(fake_session):
    session, session_factory = fake_session
    session.get.return_value = None

    repo = Repository(session_factory=session_factory)
    with pytest.raises(ValueError, match="Không tìm thấy"):
        repo.publish_version("missing")
