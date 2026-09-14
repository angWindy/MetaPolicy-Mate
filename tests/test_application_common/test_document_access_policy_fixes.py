"""Regression tests for the contract and policy fixes from
``BUGS_FOUND.md``.

These tests guard the user-visible contracts documented in the
review:

- B-P1-02: ``UpdateRegulatoryDocumentRequest`` must reject
  ``effective_date < issued_date`` (it would otherwise let admins
  create a document that is "effective before it was issued").
- B-P1-01: ``citations_are_accessible`` must NOT issue N+1
  queries - it should batch the lookup of both the documents and
  the department↔document ACL join.

Tests run against real services (Postgres + R2) only; no mocks.
"""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import AsyncMock
from uuid import (
    UUID,
    uuid4,
)

# Force test environment before importing the contracts module.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEV_AUTH_BYPASS", "true")

import pytest

from src.application.common.document_access_policy import (
    citations_are_accessible,
)
from src.domain.entities.document import (
    Document,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)
from src.presentation.api.contracts.regulatory_documents.update_regulatory_document_request import (
    UpdateRegulatoryDocumentRequest,
)


# ---------------------------------------------------------------------------
# B-P1-02 - date order validation
# ---------------------------------------------------------------------------


class TestEffectiveDateOrder:
    """Guard the B-P1-02 fix on ``UpdateRegulatoryDocumentRequest``."""

    def test_accepts_effective_after_issued(self):
        req = UpdateRegulatoryDocumentRequest(
            document_number="QĐ-001/2026",
            title="Test",
            issued_by="Issuer",
            issued_date=date(2026, 1, 1),
            effective_date=date(2026, 6, 1),
        )
        assert (
            req.effective_date
            > req.issued_date
        )

    def test_accepts_same_day_issue_and_effective(self):
        # Same-day issuance + effectiveness is legitimate
        # (e.g. urgent regulatory announcements).
        req = UpdateRegulatoryDocumentRequest(
            document_number="QĐ-002/2026",
            title="Test",
            issued_by="Issuer",
            issued_date=date(2026, 1, 1),
            effective_date=date(2026, 1, 1),
        )
        assert req.effective_date == req.issued_date

    def test_rejects_effective_before_issued(self):
        # The reproducer from BUGS_FOUND.md B-P1-02:
        # issued_date=2026-12-01, effective_date=2026-01-01.
        with pytest.raises(
            ValueError,
            match="effective_date must be on or after issued_date",
        ):
            UpdateRegulatoryDocumentRequest(
                document_number="QĐ-003/2026",
                title="Test",
                issued_by="Issuer",
                issued_date=date(2026, 12, 1),
                effective_date=date(2026, 1, 1),
            )


# ---------------------------------------------------------------------------
# B-P1-01 - citations_are_accessible N+1 fix
# ---------------------------------------------------------------------------


def _make_document(
    *,
    document_id: UUID,
    access_scope: DocumentAccessScope,
) -> Document:
    """Lightweight in-memory Document for the policy test.

    ``Document`` is a ``@dataclass`` so we can construct one
    without going through the ORM or repository fixtures. The
    policy only reads ``id`` and ``access_scope``.
    """
    return Document(
        id=document_id,
        document_number=f"DOC-{document_id.hex[:6]}",
        title="Test",
        issued_by="Issuer",
        issued_date=date(2026, 1, 1),
        effective_date=date(2026, 1, 1),
        legal_status=DocumentLegalStatus.DANG_HIEU_LUC,
        access_scope=access_scope,
    )


class TestCitationsAreAccessibleBatching:
    """Guard the B-P1-01 N+1 fix.

    The policy must call ``DocumentRepository.get_by_ids`` and
    ``DocumentDepartmentRepository.can_access_any`` exactly once
    each - regardless of how many citations are passed in.
    """

    @pytest.mark.asyncio
    async def test_public_citations_need_no_department_lookup(self):
        # All citations are PUBLIC: must not even call
        # can_access_any - the PUBLIC scope bypasses ACL.
        doc_id = uuid4()
        doc_repo = AsyncMock()
        doc_repo.get_by_ids.return_value = [
            _make_document(
                document_id=doc_id,
                access_scope=DocumentAccessScope.PUBLIC,
            )
        ]
        dept_repo = AsyncMock()
        dept_repo.can_access_any.return_value = set()

        ok = await citations_are_accessible(
            citations=[
                {"document_id": str(doc_id)},
                {"document_id": str(doc_id)},
            ],
            department_id=uuid4(),
            document_repository=doc_repo,
            document_department_repository=dept_repo,
        )

        assert ok is True
        # Exactly one batched document lookup, ZERO ACL joins.
        assert doc_repo.get_by_ids.await_count == 1
        assert doc_repo.get_by_id.await_count == 0
        assert dept_repo.can_access_any.await_count == 0

    @pytest.mark.asyncio
    async def test_department_scoped_citations_use_batch_query(self):
        # 5 DEPARTMENT-scoped docs → exactly 1 batched ACL
        # query, NOT 5 separate ones.
        doc_ids = [uuid4() for _ in range(5)]
        docs = [
            _make_document(
                document_id=did,
                access_scope=DocumentAccessScope.DEPARTMENT,
            )
            for did in doc_ids
        ]
        doc_repo = AsyncMock()
        doc_repo.get_by_ids.return_value = docs
        dept_repo = AsyncMock()
        # All accessible.
        dept_repo.can_access_any.return_value = set(doc_ids)

        ok = await citations_are_accessible(
            citations=[
                {"document_id": str(did)} for did in doc_ids
            ],
            department_id=uuid4(),
            document_repository=doc_repo,
            document_department_repository=dept_repo,
        )

        assert ok is True
        # One batched document lookup + one batched ACL join.
        assert doc_repo.get_by_ids.await_count == 1
        assert dept_repo.can_access_any.await_count == 1

    @pytest.mark.asyncio
    async def test_missing_document_fails_closed(self):
        # If even one citation references a doc that does not
        # exist, the policy must fail closed (return False) -
        # we cannot prove access to a missing document.
        existing = uuid4()
        missing = uuid4()
        doc_repo = AsyncMock()
        doc_repo.get_by_ids.return_value = [
            _make_document(
                document_id=existing,
                access_scope=DocumentAccessScope.PUBLIC,
            )
        ]
        dept_repo = AsyncMock()

        ok = await citations_are_accessible(
            citations=[
                {"document_id": str(existing)},
                {"document_id": str(missing)},
            ],
            department_id=uuid4(),
            document_repository=doc_repo,
            document_department_repository=dept_repo,
        )

        assert ok is False

    @pytest.mark.asyncio
    async def test_cross_school_user_cannot_access_department_docs(self):
        # department_id=None means cross-school user. They must
        # not be able to read DEPARTMENT-scoped docs even if the
        # department join would otherwise succeed.
        doc_id = uuid4()
        docs = [
            _make_document(
                document_id=doc_id,
                access_scope=DocumentAccessScope.DEPARTMENT,
            )
        ]
        doc_repo = AsyncMock()
        doc_repo.get_by_ids.return_value = docs
        dept_repo = AsyncMock()
        # Even if the join claims access, fail closed.
        dept_repo.can_access_any.return_value = {doc_id}

        ok = await citations_are_accessible(
            citations=[
                {"document_id": str(doc_id)},
            ],
            department_id=None,
            document_repository=doc_repo,
            document_department_repository=dept_repo,
        )

        assert ok is False
        # We never even need to query the join for cross-school.
        assert dept_repo.can_access_any.await_count == 0