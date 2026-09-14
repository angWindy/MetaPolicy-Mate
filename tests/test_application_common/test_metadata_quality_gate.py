"""Unit tests for :class:`MetadataQualityGate`.

Covers:

* Happy path: complete metadata → ``needs_human_review=False``.
* Each missing-field branch: ``document_number``, ``title``,
  ``issued_by``, ``issued_date``, ``effective_date``.
* Date-order violation: ``effective_date < issued_date``.
* Short-title branch: title with fewer than ``MIN_TITLE_LENGTH`` chars.

Tests are pure-Python and need no DB / Qdrant / R2.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

# Ensure ``src.*`` importable when running ``pytest tests/`` from the repo root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "test")

from src.application.common.metadata_quality_gate import (  # noqa: E402
    MetadataQualityGate,
)
from src.domain.entities.document import Document  # noqa: E402
from src.domain.enums.document_access_scope import DocumentAccessScope  # noqa: E402
from src.domain.enums.document_legal_status import DocumentLegalStatus  # noqa: E402


# ---------------------------------------------------------------------- #
# Fixture
# ---------------------------------------------------------------------- #


def _make_document(
    *,
    document_number: str = "188/QĐ-BGDDT",
    title: str = "Quyết định về việc ban hành Quy chế làm việc",
    issued_by: str = "Bộ Giáo dục và Đào tạo",
    issued_date: date | None = date(2026, 1, 29),
    effective_date: date | None = date(2026, 1, 29),
) -> Document:
    return Document(
        id=uuid4(),
        document_number=document_number,
        title=title,
        issued_by=issued_by,
        issued_date=issued_date,  # type: ignore[arg-type]
        effective_date=effective_date,  # type: ignore[arg-type]
        legal_status=DocumentLegalStatus.DANG_HIEU_LUC,
        access_scope=DocumentAccessScope.PUBLIC,
    )


# ---------------------------------------------------------------------- #
# Happy path
# ---------------------------------------------------------------------- #


class TestHappyPath:
    def test_complete_metadata_passes(self):
        result = MetadataQualityGate.evaluate(_make_document())
        assert result.needs_human_review is False
        assert result.document_number_valid is True
        assert result.title_valid is True
        assert result.issued_by_valid is True
        assert result.issued_date_present is True
        assert result.effective_date_present is True
        assert result.effective_after_issued is True
        assert result.rationale == ()

    def test_pure_numeric_document_number_passes(self):
        result = MetadataQualityGate.evaluate(
            _make_document(document_number="123")
        )
        assert result.document_number_valid is True
        assert result.needs_human_review is False


# ---------------------------------------------------------------------- #
# Per-field failure branches
# ---------------------------------------------------------------------- #


class TestPerFieldFailure:
    def test_missing_document_number(self):
        result = MetadataQualityGate.evaluate(
            _make_document(document_number="")
        )
        assert result.document_number_valid is False
        assert result.needs_human_review is True
        assert any("Số hiệu" in r for r in result.rationale)

    def test_malformed_document_number(self):
        # No digits — fails the canonical regex.
        result = MetadataQualityGate.evaluate(
            _make_document(document_number="abc")
        )
        assert result.document_number_valid is False
        assert result.needs_human_review is True

    def test_short_title(self):
        # 7 chars — under MIN_TITLE_LENGTH (8).
        result = MetadataQualityGate.evaluate(
            _make_document(title="Quy chế")
        )
        assert result.title_valid is False
        assert result.needs_human_review is True
        assert any("Tiêu đề" in r for r in result.rationale)

    def test_empty_title(self):
        result = MetadataQualityGate.evaluate(_make_document(title=""))
        assert result.title_valid is False
        assert result.needs_human_review is True

    def test_missing_issued_by(self):
        result = MetadataQualityGate.evaluate(
            _make_document(issued_by="")
        )
        assert result.issued_by_valid is False
        assert result.needs_human_review is True
        assert any("Cơ quan ban hành" in r for r in result.rationale)

    def test_missing_issued_date(self):
        result = MetadataQualityGate.evaluate(
            _make_document(issued_date=None)
        )
        assert result.issued_date_present is False
        assert result.needs_human_review is True
        assert any("Ngày ban hành" in r for r in result.rationale)

    def test_missing_effective_date(self):
        result = MetadataQualityGate.evaluate(
            _make_document(effective_date=None)
        )
        assert result.effective_date_present is False
        assert result.needs_human_review is True
        assert any("Ngày có hiệu lực" in r for r in result.rationale)

    def test_effective_before_issued(self):
        result = MetadataQualityGate.evaluate(
            _make_document(
                issued_date=date(2026, 6, 1),
                effective_date=date(2026, 1, 1),
            )
        )
        assert result.effective_after_issued is False
        assert result.needs_human_review is True
        assert any("hiệu lực phải sau" in r for r in result.rationale)


# ---------------------------------------------------------------------- #
# Behaviour shared across the gate
# ---------------------------------------------------------------------- #


class TestResultShape:
    def test_result_is_immutable(self):
        result = MetadataQualityGate.evaluate(_make_document())
        with pytest.raises((AttributeError, Exception)):
            result.needs_human_review = True  # type: ignore[misc]

    def test_rationale_is_tuple(self):
        # Tuple is hashable + JSON-serialisable via list().
        result = MetadataQualityGate.evaluate(_make_document())
        assert isinstance(result.rationale, tuple)
        # And the dict projection works for logging.
        assert result.to_dict()["needs_human_review"] is False
        assert isinstance(result.to_dict()["rationale"], list)

    def test_min_title_length_constant(self):
        # Documented behaviour — gate's contract.
        assert MetadataQualityGate.MIN_TITLE_LENGTH == 8
