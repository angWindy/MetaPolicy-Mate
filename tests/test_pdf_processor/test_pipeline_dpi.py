"""Unit tests for the per-page DPI selection in :mod:`pdf_processor.pipeline`.

These tests guard the multi-tier DPI strategy that the pipeline applies
when rendering each page for OCR:

* ``cover_dpi`` — first page only. Keeps ``document_number`` / issued_by
  legible.
* ``body_dpi`` — every other page. Halves the per-page compute.
* ``last_page_dpi`` — last page only, when not ``None``. Legal documents
  routinely carry signatures / stamps on the final page, so a 300-DPI
  downscale degrades the most critical metadata capture.

The previous implementation hardcoded ``page_dpi = cover_dpi if page_num
== 0 else body_dpi`` and silently degraded signature OCR quality on
multi-page legal documents. These tests pin the new policy.
"""

from __future__ import annotations

import pytest

from src.ingestion.pdf_processor.pipeline import (
    PDFProcessingPipeline,
    PipelineConfig,
)

# ─────────────────────────────────────────────────────────────────────────────
# PipelineConfig defaults
# ─────────────────────────────────────────────────────────────────────────────


def test_pipeline_config_default_last_page_dpi_matches_cover() -> None:
    """``last_page_dpi`` defaults to ``cover_dpi`` (600) so the pipeline
    keeps the last page at high resolution out of the box — opt-out via
    ``last_page_dpi=None`` for documents that don't need the bump.
    """
    cfg = PipelineConfig()
    assert cfg.last_page_dpi == cfg.cover_dpi
    assert cfg.last_page_dpi == 600


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_page_dpi policy table
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("page_num", "total_pages", "cover_dpi", "body_dpi", "last_page_dpi", "expected"),
    [
        # Single-page document: the first page IS the last page. Cover applies.
        (0, 1, 600, 300, 600, 600),
        (0, 1, 600, 300, None, 600),  # last_page_dpi=None doesn't matter for cover
        # Two-page document: cover + last, no body in between.
        (0, 2, 600, 300, 600, 600),
        (1, 2, 600, 300, 600, 600),
        # Five-page document, default last_page_dpi=600: cover, 3×body, last=cover.
        (0, 5, 600, 300, 600, 600),
        (1, 5, 600, 300, 600, 300),
        (2, 5, 600, 300, 600, 300),
        (3, 5, 600, 300, 600, 300),
        (4, 5, 600, 300, 600, 600),
        # Five-page document, last_page_dpi=None: cover, 4×body, no last bump.
        (0, 5, 600, 300, None, 600),
        (1, 5, 600, 300, None, 300),
        (2, 5, 600, 300, None, 300),
        (3, 5, 600, 300, None, 300),
        (4, 5, 600, 300, None, 300),
        # Five-page document, last_page_dpi distinct from cover (e.g. user
        # wants 450 DPI for last page, not 600).
        (4, 5, 600, 300, 450, 450),
        # Custom cover/body for short memos.
        (0, 3, 200, 150, None, 200),
        (1, 3, 200, 150, None, 150),
        (2, 3, 200, 150, None, 150),
    ],
)
def test_resolve_page_dpi_policy_table(
    page_num: int,
    total_pages: int,
    cover_dpi: int,
    body_dpi: int,
    last_page_dpi: int | None,
    expected: int,
) -> None:
    """The DPI resolver is a pure function of (page_num, total_pages,
    cover_dpi, body_dpi, last_page_dpi). The matrix above pins every
    relevant combination so a future refactor that gets the cover/last
    ordering wrong (e.g. swapping the conditions and dropping the
    last-page bump) is caught immediately."""
    got = PDFProcessingPipeline._resolve_page_dpi(
        page_num,
        total_pages=total_pages,
        cover_dpi=cover_dpi,
        body_dpi=body_dpi,
        last_page_dpi=last_page_dpi,
    )
    assert got == expected, (
        f"page {page_num}/{total_pages} cover={cover_dpi} body={body_dpi} "
        f"last={last_page_dpi}: got {got} expected {expected}"
    )


def test_resolve_page_dpi_zero_total_pages_falls_back_to_body() -> None:
    """Defensive: an empty document (no pages) shouldn't crash. The
    resolver falls back to ``body_dpi`` so a downstream render call
    doesn't divide by zero or pick a nonsensical value.
    """
    assert (
        PDFProcessingPipeline._resolve_page_dpi(
            0,
            total_pages=0,
            cover_dpi=600,
            body_dpi=300,
            last_page_dpi=600,
        )
        == 300
    )


def test_resolve_page_dpi_last_page_dpi_zero_is_not_disabled() -> None:
    """The "disabled" sentinel for ``last_page_dpi`` is ``None`` (not
    ``0``). Pinning this so a future refactor doesn't accidentally
    treat ``0`` as "disabled" and degrade the last page to literal
    zero-DPI rendering."""
    # last_page_dpi=0 (explicitly set, not None) -> 0 is used as the DPI.
    assert (
        PDFProcessingPipeline._resolve_page_dpi(
            4,
            total_pages=5,
            cover_dpi=600,
            body_dpi=300,
            last_page_dpi=0,
        )
        == 0
    )
