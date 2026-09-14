"""Metadata quality gate.

Single source of truth for deciding whether a freshly-parsed
document version has enough structured metadata to be auto-promoted
into the RAG pipeline.

Why a dedicated module (per ``AGENTS.md`` cross-layer rule §7):
the gate is consulted by:

* :class:`DigitizeDocumentHandler` — wires the result into the
  ``version.processing_status`` (``approved`` vs ``pending_review``).
* ``scripts/ocr/cleanup_corpus_metadata.py`` — sweeps 150 historical
  PDFs and decides which need human review.
* Future ingestion workers / cron jobs — same evaluation, no
  duplicated logic.

The gate is a *pure function*: it inspects the parsed document /
metadata and returns a :class:`MetadataQualityResult` describing what
passed and what failed. It never mutates state or talks to the
database. That keeps it trivially testable and safe to invoke from
background workers.

The criteria mirror :func:`src.domain.validators.document_validator.
validate_required_metadata` but are expressed in terms of the
:class:`src.domain.entities.document.Document` entity so the caller
does not have to re-shape the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.entities.document import Document
from src.domain.validators.document_validator import (
    validate_document_number,
    validate_issued_by,
)


# ---------------------------------------------------------------------- #
# Result type
# ---------------------------------------------------------------------- #


@dataclass(frozen=True)
class MetadataQualityResult:
    """Outcome of evaluating a document's metadata quality.

    Fields are intentionally exhaustive — every criterion has its own
    boolean so the admin UI can render a "fix list" without re-running
    the gate.
    """

    document_number_valid: bool = False
    title_valid: bool = False
    issued_by_valid: bool = False
    issued_date_present: bool = False
    effective_date_present: bool = False
    effective_after_issued: bool = False
    needs_human_review: bool = True
    rationale: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """JSON-friendly projection (rationale becomes a list)."""
        return {
            "document_number_valid": self.document_number_valid,
            "title_valid": self.title_valid,
            "issued_by_valid": self.issued_by_valid,
            "issued_date_present": self.issued_date_present,
            "effective_date_present": self.effective_date_present,
            "effective_after_issued": self.effective_after_issued,
            "needs_human_review": self.needs_human_review,
            "rationale": list(self.rationale),
        }


# ---------------------------------------------------------------------- #
# Gate
# ---------------------------------------------------------------------- #


class MetadataQualityGate:
    """Decide whether a document's metadata is complete enough for RAG.

    The gate is *pure*: it does not touch the database, the Qdrant
    index, or any global state. Every consumer
    (digitize handler, cleanup script, future cron) gets the same
    deterministic answer.

    A document PASSES when ALL of these are true:

    * ``document_number`` matches the canonical regex
      (``123`` or ``123/QĐ-ĐHBK``).
    * ``title`` is non-empty and at least ``MIN_TITLE_LENGTH`` chars.
    * ``issued_by`` is non-empty.
    * ``issued_date`` is set.
    * ``effective_date`` is set AND >= ``issued_date``.

    Otherwise the gate fails; the caller decides what to do
    (auto-approve, push to admin queue, ...).
    """

    #: Minimum length for ``title``. Shorter titles are almost always
    #: OCR artefacts — file name fragments, page headers, etc.
    MIN_TITLE_LENGTH: int = 8

    @classmethod
    def evaluate(cls, document: Document) -> MetadataQualityResult:
        """Return a :class:`MetadataQualityResult` for ``document``.

        The function never raises on bad input — missing fields are
        recorded as ``False`` and contribute to ``needs_human_review``.
        Type errors (e.g. ``document`` is ``None``) are *not* caught
        here; we let them bubble so a misuse surfaces immediately.
        """
        rationale: list[str] = []

        document_number_valid = validate_document_number(
            document.document_number or ""
        )
        if not document_number_valid:
            rationale.append(
                "Số hiệu văn bản không đúng định dạng hoặc bị trống."
            )

        title_raw = (document.title or "").strip()
        title_valid = (
            len(title_raw) >= cls.MIN_TITLE_LENGTH
        )
        if not title_valid:
            rationale.append(
                f"Tiêu đề quá ngắn (< {cls.MIN_TITLE_LENGTH} ký tự) "
                "hoặc bị trống."
            )

        issued_by_valid = validate_issued_by(document.issued_by)
        if not issued_by_valid:
            rationale.append("Cơ quan ban hành bị trống.")

        issued_date_present = document.issued_date is not None
        if not issued_date_present:
            rationale.append("Ngày ban hành bị trống.")

        effective_date_present = document.effective_date is not None
        if not effective_date_present:
            rationale.append("Ngày có hiệu lực bị trống.")

        effective_after_issued = True
        if (
            issued_date_present
            and effective_date_present
            and document.effective_date is not None
            and document.issued_date is not None
            and document.effective_date < document.issued_date
        ):
            effective_after_issued = False
            rationale.append(
                "Ngày có hiệu lực phải sau hoặc bằng ngày ban hành."
            )

        needs_human_review = not (
            document_number_valid
            and title_valid
            and issued_by_valid
            and issued_date_present
            and effective_date_present
            and effective_after_issued
        )

        return MetadataQualityResult(
            document_number_valid=document_number_valid,
            title_valid=title_valid,
            issued_by_valid=issued_by_valid,
            issued_date_present=issued_date_present,
            effective_date_present=effective_date_present,
            effective_after_issued=effective_after_issued,
            needs_human_review=needs_human_review,
            rationale=tuple(rationale),
        )


__all__ = [
    "MetadataQualityGate",
    "MetadataQualityResult",
]
