"""Unit tests for :class:`AutoApproveReviewHandler`.

Covers:

* Happy path: pending_review + complete metadata → APPROVED.
* Gate still fails → status stays PENDING_REVIEW, returns fix list.
* Wrong source state (e.g. PARSED) → ConflictException.
* Missing document or version → NotFoundException.

Tests use mocked repositories — no DB / Qdrant / R2 needed.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "test")

from src.application.common.exceptions.conflict_exception import (  # noqa: E402
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (  # noqa: E402
    NotFoundException,
)
from src.application.common.metadata_quality_gate import (  # noqa: E402
    MetadataQualityGate,
)
from src.application.features.documents.review.auto_approve_review_command import (  # noqa: E402
    AutoApproveReviewCommand,
)
from src.application.features.documents.review.auto_approve_review_handler import (  # noqa: E402
    AutoApproveReviewHandler,
)
from src.domain.entities.document import Document  # noqa: E402
from src.domain.entities.document_version import DocumentVersion  # noqa: E402
from src.domain.enums.document_access_scope import DocumentAccessScope  # noqa: E402
from src.domain.enums.document_legal_status import DocumentLegalStatus  # noqa: E402
from src.domain.enums.document_processing_status import (  # noqa: E402
    DocumentProcessingStatus,
    ProcessingStatus,
)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #


def _make_document(
    *,
    document_number: str = "188/QĐ-BGDDT",
    title: str = "Quyết định về việc ban hành Quy chế làm việc",
    issued_by: str = "Bộ Giáo dục và Đào tạo",
    issued_date: date = date(2026, 1, 29),
    effective_date: date = date(2026, 1, 29),
) -> Document:
    return Document(
        id=uuid4(),
        document_number=document_number,
        title=title,
        issued_by=issued_by,
        issued_date=issued_date,
        effective_date=effective_date,
        legal_status=DocumentLegalStatus.DANG_HIEU_LUC,
        access_scope=DocumentAccessScope.PUBLIC,
    )


def _make_version(
    *,
    document: Document,
    processing_status: DocumentProcessingStatus = (
        DocumentProcessingStatus.PENDING_REVIEW
    ),
) -> DocumentVersion:
    return DocumentVersion(
        id=uuid4(),
        document_id=document.id,
        version_number=1,
        processing_status=processing_status,
        checksum="x" * 64,
        source_filename="test.pdf",
        object_key="ocr-bench/test.pdf",
        content_type="application/pdf",
        size_bytes=1024,
    )


def _build_handler(
    *,
    version: DocumentVersion | None,
    document: Document | None,
) -> tuple[
    AutoApproveReviewHandler,
    AsyncMock,
    AsyncMock,
    AsyncMock,
]:
    """Build a handler with mocked repositories. Returns the mocks so
    individual tests can inspect calls."""
    version_repo = AsyncMock()
    version_repo.get_by_id.return_value = version

    document_repo = AsyncMock()
    document_repo.get_by_id.return_value = document

    uow = AsyncMock()
    uow.save_changes = AsyncMock(return_value=None)

    handler = AutoApproveReviewHandler(
        document_repository=document_repo,
        document_version_repository=version_repo,
        unit_of_work=uow,
    )
    return handler, version_repo, document_repo, uow


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestAutoApproveHappyPath:
    async def test_pending_review_with_complete_metadata_flips_to_approved(
        self,
    ):
        document = _make_document()
        version = _make_version(document=document)
        handler, version_repo, _document_repo, uow = _build_handler(
            version=version, document=document
        )

        result = await handler.handle(
            AutoApproveReviewCommand(
                version_id=version.id,
                admin_id=uuid4(),
                notes="gate now passes after manual OCR retry",
            )
        )

        assert result.auto_approved is True
        assert result.status == ProcessingStatus.APPROVED
        assert result.approved_at is not None
        assert result.validation_result["needs_human_review"] is False

        # Version was updated and committed.
        assert version_repo.update.await_count == 1
        assert uow.save_changes.await_count == 1
        assert version.processing_status == DocumentProcessingStatus.APPROVED
        assert "auto-approve" in (version.review_notes or "")


@pytest.mark.asyncio
class TestGateStillFails:
    async def test_pending_review_with_missing_metadata_stays_pending(
        self,
    ):
        document = _make_document(
            document_number="",  # missing → gate fails
        )
        version = _make_version(document=document)
        handler, version_repo, _document_repo, uow = _build_handler(
            version=version, document=document
        )

        result = await handler.handle(
            AutoApproveReviewCommand(
                version_id=version.id,
                admin_id=uuid4(),
            )
        )

        assert result.auto_approved is False
        assert result.status == ProcessingStatus.PENDING_REVIEW
        assert result.approved_at is None
        assert result.validation_result["needs_human_review"] is True
        assert len(result.validation_result["rationale"]) > 0

        # Status not flipped; no commit.
        assert version_repo.update.await_count == 0
        assert uow.save_changes.await_count == 0
        assert version.processing_status == (
            DocumentProcessingStatus.PENDING_REVIEW
        )


@pytest.mark.asyncio
class TestWrongSourceState:
    async def test_parsed_state_rejected(self):
        document = _make_document()
        version = _make_version(
            document=document,
            processing_status=DocumentProcessingStatus.PARSED,
        )
        handler, *_ = _build_handler(
            version=version, document=document
        )

        with pytest.raises(ConflictException, match="Cannot auto-approve"):
            await handler.handle(
                AutoApproveReviewCommand(
                    version_id=version.id,
                    admin_id=uuid4(),
                )
            )

    async def test_published_state_rejected(self):
        document = _make_document()
        version = _make_version(
            document=document,
            processing_status=DocumentProcessingStatus.PUBLISHED,
        )
        handler, *_ = _build_handler(
            version=version, document=document
        )

        with pytest.raises(ConflictException):
            await handler.handle(
                AutoApproveReviewCommand(
                    version_id=version.id,
                    admin_id=uuid4(),
                )
            )


@pytest.mark.asyncio
class TestMissingEntities:
    async def test_missing_version_raises_not_found(self):
        handler, *_ = _build_handler(version=None, document=None)
        with pytest.raises(NotFoundException):
            await handler.handle(
                AutoApproveReviewCommand(
                    version_id=uuid4(),
                    admin_id=uuid4(),
                )
            )

    async def test_missing_document_raises_not_found(self):
        document = _make_document()
        version = _make_version(document=document)
        # Document lookup returns None.
        handler, *_ = _build_handler(
            version=version, document=None
        )
        with pytest.raises(NotFoundException):
            await handler.handle(
                AutoApproveReviewCommand(
                    version_id=version.id,
                    admin_id=uuid4(),
                )
            )


# ---------------------------------------------------------------------- #
# Sanity: MetadataQualityGate is consistent with the handler
# ---------------------------------------------------------------------- #


def test_gate_and_handler_agree_on_criteria():
    """Guard against silent drift between the gate and the handler."""
    # Gate accepts canonical number formats.
    assert MetadataQualityGate.evaluate(_make_document()).needs_human_review is False
    # Gate rejects blank document_number.
    assert MetadataQualityGate.evaluate(
        _make_document(document_number="")
    ).needs_human_review is True
