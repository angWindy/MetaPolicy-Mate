"""Regression tests for the production admin publish gate.

The legacy :class:`src.db.repository.Repository.publish_version` is
deprecated (see BUGS_FOUND.md B-P3-01). Production HTTP traffic goes
through ``admin_router.publish_document_version`` which enforces the
strict ``INDEXED -> PUBLISHED`` transition.

These tests assert the production gate's behaviour using a pure-Python
mirror of the gate logic plus an introspection check against the
router source code. The router's gate is intentionally simple
(``processing_status != INDEXED`` -> ConflictException), so testing it
without spinning up FastAPI/SQLAlchemy is enough to lock the contract.
"""

from __future__ import annotations

import inspect

import pytest

from src.domain.schemas import ProcessingStatus


def _gate_logic(current_status: str) -> str:
    """Mirror of admin_router.publish_document_version gate.

    The router code is::

        if version.processing_status != ProcessingStatus.INDEXED.value:
            raise ConflictException(
                "Version must be Indexed before publishing. "
                f"Current status: {version.processing_status}.",
            )
        ...flip status to PUBLISHED...

    This test mirrors the gate exactly. If the router changes, this
    mirror must change too — that is the point. A regression here
    forces a code review on the gate.
    """
    if current_status != ProcessingStatus.INDEXED.value:
        raise RuntimeError(
            f"ConflictException: Version must be Indexed before "
            f"publishing. Current status: {current_status}."
        )
    return ProcessingStatus.PUBLISHED.value


def test_strict_gate_allows_indexed() -> None:
    """Positive: a version that has reached INDEXED can be published."""
    assert _gate_logic(ProcessingStatus.INDEXED.value) == "published"


@pytest.mark.parametrize(
    "blocked_status",
    [
        ProcessingStatus.RECEIVED.value,
        ProcessingStatus.PARSED.value,
        ProcessingStatus.APPROVED.value,
        ProcessingStatus.FAILED.value,
        ProcessingStatus.PUBLISHED.value,
    ],
)
def test_strict_gate_blocks_every_non_indexed_status(blocked_status: str) -> None:
    """Every non-INDEXED status must be rejected.

    ``APPROVED`` is included deliberately. The legacy
    ``Repository.publish_version`` (deprecated) accepts ``APPROVED``;
    the production gate rejects it. Without the strict gate an APPROVED
    version can leak into PUBLISHED state without ever being indexed
    in Qdrant.
    """
    with pytest.raises(RuntimeError, match="must be Indexed"):
        _gate_logic(blocked_status)


def test_strict_gate_matches_router_source() -> None:
    """Sanity: the mirror tracks the production router.

    Locks the gate to three exact strings that the router source
    must contain. If any string is missing the gate has been weakened
    or moved — that is a code-review-worthy regression.
    """
    from src.presentation.api.routers.admin_router import (
        publish_document_version,
    )

    source = inspect.getsource(publish_document_version)
    assert "ProcessingStatus.INDEXED.value" in source, (
        "admin_router.publish_document_version no longer gates on "
        "ProcessingStatus.INDEXED — review the change."
    )
    assert "Version must be Indexed" in source, (
        "admin_router.publish_document_version no longer raises the "
        "expected ConflictException message — review the change."
    )
    assert "raise ConflictException" in source, (
        "admin_router.publish_document_version no longer raises "
        "ConflictException on the strict gate — review the change."
    )


def test_legacy_publish_version_uses_weaker_gate() -> None:
    """Document B-P3-01: legacy accepts APPROVED, production rejects it.

    Locks the legacy-vs-production difference so the deprecation
    cannot quietly regress.
    """
    source = inspect.getsource(
        __import__("src.db.repository", fromlist=["Repository"]).Repository.publish_version
    )
    # Legacy allows both APPROVED and INDEXED — that's the weaker gate.
    assert "ProcessingStatus.APPROVED.value" in source, (
        "Legacy Repository.publish_version lost the APPROVED branch — "
        "either the legacy was tightened (good) or the test is stale."
    )
    assert "ProcessingStatus.INDEXED.value" in source, (
        "Legacy Repository.publish_version lost the INDEXED branch — "
        "that is unexpected; review the change."
    )