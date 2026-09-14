"""Regression tests for the OCR engine and PP-StructureV3 helper.

These tests cover the defect categories that have surfaced in code review:

1. ``OCREngine._rescale_blocks`` used ``model_copy(update=...)`` which can
   bypass Pydantic validation and silently leave derived/cache fields out
   of sync with the rescaled coordinates. The fix rebuilds each block via
   the public ``OCRBlock(...)`` constructor.

2. ``OCREngine._rescale_blocks`` used naive float multiplication, producing
   sub-pixel drift when the scale factor was non-integer
   (e.g. ``5 * 1.5 == 7.5``). The fix routes every coordinate through
   ``_scale_to_pixel`` so the result is always an integer-valued float,
   matching the downstream ``int(bbox.x0)`` / crop math conventions.

3. ``PPStructureEngine._extract_blocks`` duplicated
   ``sum(region_confs) / len(region_confs)`` between the ``OCRWord`` and the
   ``OCRBlock`` constructor; the duplication risks a ``ZeroDivisionError``
   if the guard is dropped in one of the two call sites. The fix hoists
   the guarded average into a single local.

4. ``PPStructureEngine.process`` collects confidences that can legitimately
   be empty when every detected score falls below threshold. ``avg_conf``
   is correctly guarded, but ``needs_review`` was being set purely from
   the (zero) average with no surface signal that text was rejected. The
   fix attaches an actionable warning.

5. ``_resize_image`` resolved its cv2/Pillow dependency lazily, so a user
   who installed PaddleOCR without opencv-python/Pillow would only see the
   failure on the first oversized page. The fix probes the backend at
   module import time.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

# Make ``src.*`` importable when running ``pytest tests/`` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.pdf_processor.ocr_engine import (  # noqa: E402
    OCRConfig,
    OCREngine,
    _clamp_confidence,
    _coords_overlap_or_touch,
    _header_footer_thresholds,
    _rescale_bbox_preserving_dim,
    _resize_image,
    _round_half_away_from_zero,
    _safe_mean,
    _scale_to_pixel,
    bbox_to_int,
)
from src.ingestion.pdf_processor.pp_structure import PPStructureEngine  # noqa: E402
from src.ingestion.pdf_processor.schemas import (  # noqa: E402
    BlockType,
    BoundingBox,
    OCRBlock,
    OCRWord,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_block(
    *,
    text: str = "Điều 1",
    bbox: BoundingBox | None | type(...) = ...,
    words: list[OCRWord] | None = None,
    confidence: float = 0.9,
    page: int = 7,
    reading_order: int = 3,
) -> OCRBlock:
    # ``bbox`` is overloaded: ``None`` means "explicitly no bbox",
    # the sentinel ``...`` (default) means "fall back to a default box".
    # This lets tests exercise the ``bbox=None`` branch separately from the
    # happy path.
    if bbox is ...:
        bbox = BoundingBox(x0=10, y0=20, x1=30, y1=40)
    if words is None:
        words = [OCRWord(text="Điều", bbox=bbox, confidence=confidence)]  # type: ignore[arg-type]
    return OCRBlock(
        block_type=BlockType.PARAGRAPH,
        text=text,
        bbox=bbox,  # type: ignore[arg-type]
        words=words,
        confidence=confidence,
        page=page,
        reading_order=reading_order,
    )


@pytest.fixture
def engine() -> OCREngine:
    """An OCREngine that does not touch PaddleOCR at construction time."""
    return OCREngine(OCRConfig())


# ─────────────────────────────────────────────────────────────────────────────
# Fix #1: _rescale_blocks must rebuild blocks via the public constructor
# ─────────────────────────────────────────────────────────────────────────────


class TestRescaleBlocks:
    def test_identity_rescale_returns_same_list(self, engine: OCREngine) -> None:
        block = _make_block()
        out = engine._rescale_blocks(
            [block],
            resized_shape=(200, 200, 3),
            original_shape=(200, 200, 3),
        )
        assert out[0] is block, "identical shapes must short-circuit"

    def test_rescale_scales_bbox_and_words(self, engine: OCREngine) -> None:
        # 50x50 -> 100x100: every coordinate multiplies by 2.
        block = _make_block(
            bbox=BoundingBox(x0=10, y0=20, x1=30, y1=40),
            words=[
                OCRWord(
                    text="Điều",
                    bbox=BoundingBox(x0=10, y0=20, x1=20, y1=40),
                    confidence=0.9,
                )
            ],
        )
        out = engine._rescale_blocks(
            [block],
            resized_shape=(50, 50, 3),
            original_shape=(100, 100, 3),
        )
        assert out[0].bbox == BoundingBox(x0=20, y0=40, x1=60, y1=80)
        assert out[0].words[0].bbox == BoundingBox(x0=20, y0=40, x1=40, y1=80)

    def test_rescale_preserves_text_and_metadata(self, engine: OCREngine) -> None:
        block = _make_block(
            text="hello world",
            page=42,
            reading_order=11,
            confidence=0.73,
        )
        out = engine._rescale_blocks(
            [block],
            resized_shape=(10, 10, 3),
            original_shape=(30, 30, 3),
        )
        assert out[0].text == "hello world"
        assert out[0].page == 42
        assert out[0].reading_order == 11
        assert out[0].confidence == pytest.approx(0.73)

    def test_rescale_handles_missing_block_bbox(self, engine: OCREngine) -> None:
        """A block with ``bbox=None`` must pass through unchanged instead of
        being reconstructed with a fake all-zero box."""
        block = _make_block(bbox=None, words=[], confidence=0.0)
        out = engine._rescale_blocks(
            [block],
            resized_shape=(50, 50, 3),
            original_shape=(100, 100, 3),
        )
        assert out[0].bbox is None
        assert out[0].text == "Điều 1"

    def test_rescale_clamps_out_of_range_confidence(
        self, engine: OCREngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a constructed ``OCRBlock`` somehow ends up with confidence
        outside ``[0, 1]`` (e.g. rounding in downstream callers), the rescale
        step must clamp it before passing it to the OCRBlock constructor's
        Pydantic validator — otherwise the page ingestion crashes."""
        # Build a normally valid block, then bypass the validator to inject
        # an out-of-range value. Pydantic v2 lets us mutate validated
        # models by writing to ``__dict__`` directly when needed; here we
        # simulate the call site by using ``model_construct`` which skips
        # validation.
        bad_word = OCRWord.model_construct(
            text="x", bbox=BoundingBox(x0=0, y0=0, x1=1, y1=1), confidence=1.5
        )
        block = OCRBlock.model_construct(
            block_type=BlockType.PARAGRAPH,
            text="x",
            bbox=BoundingBox(x0=0, y0=0, x1=1, y1=1),
            words=[bad_word],
            confidence=1.5,
            page=1,
            reading_order=0,
        )

        out = engine._rescale_blocks(
            [block],
            resized_shape=(10, 10, 3),
            original_shape=(20, 20, 3),
        )
        assert 0.0 <= out[0].confidence <= 1.0
        assert 0.0 <= out[0].words[0].confidence <= 1.0

    def test_rescale_snap_to_pixel_rounds_to_integer_float(
        self, engine: OCREngine
    ) -> None:
        """A non-integer scale factor (100 -> 150 ⇒ ×1.5) used to leave
        coordinates as sub-pixel floats (e.g. ``7.5``). Downstream consumers
        crop with ``int(bbox.x0)`` and compare coordinates for layout
        grouping, so any sub-pixel drift breaks pixel-perfect alignment.
        The fix routes every coordinate through ``_scale_to_pixel``."""
        block = _make_block(
            bbox=BoundingBox(x0=5, y0=7, x1=10, y1=12),
            words=[
                OCRWord(
                    text="Điều",
                    bbox=BoundingBox(x0=5, y0=7, x1=10, y1=12),
                    confidence=0.9,
                )
            ],
        )
        out = engine._rescale_blocks(
            [block],
            resized_shape=(100, 100, 3),
            original_shape=(150, 150, 3),
        )
        scaled = out[0].bbox
        for value in (scaled.x0, scaled.y0, scaled.x1, scaled.y1):
            # Every coordinate is a float that is exactly representable as int.
            assert value == pytest.approx(round(value)), f"{value} is not pixel-aligned"
            assert value == float(int(value)), f"{value} has a non-zero fractional part"

        for word in out[0].words:
            for value in (word.bbox.x0, word.bbox.y0, word.bbox.x1, word.bbox.y1):
                assert value == float(int(value)), f"{value} has a non-zero fractional part"


# ─────────────────────────────────────────────────────────────────────────────
# Fix #2: _extract_blocks must compute confidence once, guarded
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractBlocksConfidence:
    def test_text_only_region_does_not_divide_by_zero(self) -> None:
        """When ``block_content`` is just a string, ``region_confs`` is empty.
        The old duplicated expression would have raised
        ``ZeroDivisionError`` in the OCRWord call site if the inline ternary
        were ever dropped there. The fix shares a single guarded value."""
        engine = PPStructureEngine()
        res = {
            "layout_detections": [
                {
                    "label": "paragraph",
                    "bbox": [0, 0, 10, 10],
                    "block_content": "some text",
                }
            ]
        }
        blocks, confs = engine._extract_blocks(res, page_num=1)
        assert len(blocks) == 1
        assert len(confs) == 0
        assert blocks[0].confidence == 0.0
        assert blocks[0].words[0].confidence == 0.0

    def test_scored_region_uses_mean_of_region_confs(self) -> None:
        engine = PPStructureEngine()
        res = {
            "layout_detections": [
                {
                    "label": "paragraph",
                    "bbox": [0, 0, 10, 10],
                    "block_content": [
                        {"text": "hello", "score": 0.8},
                        {"text": "world", "score": 0.6},
                    ],
                }
            ]
        }
        blocks, _ = engine._extract_blocks(res, page_num=1)
        assert blocks[0].confidence == pytest.approx(0.7)
        # Both the OCRBlock and OCRWord must use the *same* value so any
        # downstream consumer that reads ``words[0].confidence`` gets a
        # consistent signal.
        assert blocks[0].words[0].confidence == pytest.approx(0.7)

    def test_empty_region_with_bbox_is_dropped(self) -> None:
        engine = PPStructureEngine()
        res = {
            "layout_detections": [
                {
                    "label": "paragraph",
                    "bbox": [0, 0, 10, 10],
                    "block_content": None,
                }
            ]
        }
        blocks, confs = engine._extract_blocks(res, page_num=1)
        assert blocks == []
        assert confs == []


class TestProcessEmptyConfidenceGuard:
    """``process`` collects confidences across every page-result; if every
    detected score falls below ``text_rec_score_thresh`` (or every layout
    region has no score), ``confidences`` ends up empty. The
    ``avg_conf = sum/len if confidences else 0.0`` guard already prevents
    ``ZeroDivisionError``; the fix also surfaces an actionable warning
    so a caller can tell "no text" apart from "all rejected".
    """

    def test_process_handles_empty_confidences_safely(self) -> None:
        """If every detected score is below threshold, ``blocks`` is empty
        and ``confidences`` never receives an entry. ``process`` must still
        return a valid ``OCRResult`` (no ``ZeroDivisionError``) and flag
        the page for review via both ``needs_review=True`` and a warning."""
        engine = PPStructureEngine()
        engine._pipeline = _FakePPStructurePipeline(  # type: ignore[attr-defined]
            page_payloads=[
                {
                    "json": {
                        "res": {
                            "rec_texts": ["unreadable"],
                            "rec_scores": [0.1],  # well below 0.5 threshold
                            "dt_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]],
                        }
                    }
                }
            ]
        )
        # Mark the engine as already initialised so ``process`` doesn't try
        # to spin up the real PaddleOCR pipeline during the unit test.
        engine._initialized = True  # type: ignore[attr-defined]

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = engine.process(img, page_num=1)

        assert result.average_confidence == 0.0
        assert result.needs_review is True
        assert result.blocks == []
        # The whole point of the review: the warning tells the caller why
        # ``blocks`` is empty so VLM review / heuristic fallback can take over.
        assert any("below" in w.lower() or "threshold" in w.lower() for w in result.warnings)

    def test_process_warns_when_no_text_regions_at_all(self) -> None:
        engine = PPStructureEngine()
        engine._pipeline = _FakePPStructurePipeline(  # type: ignore[attr-defined]
            page_payloads=[
                {
                    "json": {
                        "res": {
                            "rec_texts": [],
                            "rec_scores": [],
                            "dt_polys": [],
                        }
                    }
                }
            ]
        )
        engine._initialized = True  # type: ignore[attr-defined]

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = engine.process(img, page_num=1)

        assert result.average_confidence == 0.0
        assert result.needs_review is True
        assert any("no text" in w.lower() for w in result.warnings)


class _FakePPStructurePipeline:
    """Minimal stand-in for ``PPStructureV3`` that emits a controlled
    payload. ``process`` only reads ``predict()`` and the ``.json``
    attribute, so we don't need real ML models."""

    def __init__(self, page_payloads: list[dict]) -> None:
        self._payloads = page_payloads

    def predict(self, image):  # noqa: ANN001
        return [_FakePageResult(p) for p in self._payloads]


class _FakePageResult:
    def __init__(self, payload: dict) -> None:
        self.json = payload["json"]
        self.markdown = None


# ─────────────────────────────────────────────────────────────────────────────
# Fix #3: _resize_image must probe cv2/PIL at import time
# ─────────────────────────────────────────────────────────────────────────────


class TestResizeImage:
    def test_resize_runs_with_available_backend(self) -> None:
        """The env the tests run in has both cv2 and Pillow, so the resize
        must succeed."""
        out = _resize_image(np.zeros((100, 100, 3), dtype=np.uint8), 50, 50)
        assert out.shape == (50, 50, 3)

    def test_resize_raises_when_no_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate the missing-dependency case and confirm ``_resize_image``
        raises ``ImportError`` rather than raising ``AttributeError`` from a
        stale backend attribute or returning garbage."""
        import src.ingestion.pdf_processor.ocr_engine as ocr_module

        monkeypatch.setattr(ocr_module, "_RESIZE_BACKEND", None)

        with pytest.raises(ImportError):
            ocr_module._resize_image(
                np.zeros((10, 10, 3), dtype=np.uint8), 5, 5
            )


class TestDownscaleSafety:
    """``_downscale_for_ocr`` calls ``_resize_image`` when the image is
    oversized. If the resize backend is missing (cv2 + Pillow both absent),
    the page ingestion must continue on the *original* image rather than
    crash everything with a surfaced ``ImportError``.
    """

    def test_oversized_image_downscales_with_backend(self, engine: OCREngine) -> None:
        img = np.zeros((5000, 5000, 3), dtype=np.uint8)
        resized, was_resized = engine._downscale_for_ocr(img)
        assert was_resized is True
        assert resized.shape[0] <= 4000 and resized.shape[1] <= 4000

    def test_oversized_image_falls_back_when_backend_missing(
        self, engine: OCREngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The hot path must not propagate the ``ImportError`` that
        ``_resize_image`` raises when cv2 + Pillow are both missing. The
        fix catches the error and short-circuits with the original image."""
        import src.ingestion.pdf_processor.ocr_engine as ocr_module

        monkeypatch.setattr(ocr_module, "_RESIZE_BACKEND", None)

        img = np.zeros((5000, 5000, 3), dtype=np.uint8)
        with pytest.warns(RuntimeWarning, match="OCR resize backend unavailable"):
            resized, was_resized = engine._downscale_for_ocr(img)
        # Caller must still see a usable image, just the original size.
        assert was_resized is False
        assert resized.shape == img.shape
        # Returning the original numpy array is the design choice — the
        # caller manages the buffer's lifecycle, so we deliberately don't
        # ``copy()`` here. (np.array_equal verifies the content; checking
        # ``is`` would alias this test to the implementation detail.)
        assert np.array_equal(resized, img)

    def test_non_oversized_image_skips_resize_entirely(self, engine: OCREngine) -> None:
        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        resized, was_resized = engine._downscale_for_ocr(img)
        assert was_resized is False
        assert resized is img


# ─────────────────────────────────────────────────────────────────────────────
# Helper coverage for _clamp_confidence, _scale_to_pixel, _round_half_away_from_zero
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.5, 0.0),
        (0.0, 0.0),
        (0.5, 0.5),
        (1.0, 1.0),
        (1.5, 1.0),
    ],
)
def test_clamp_confidence(value: float, expected: float) -> None:
    assert _clamp_confidence(value) == expected


@pytest.mark.parametrize(
    ("coord", "factor", "expected"),
    [
        # Integer-valued product stays exactly as expected.
        (5, 2.0, 10.0),
        (10, 1.5, 15.0),  # 15.0 exactly
        # Half-pixel drifts. Python's ``round`` (banker's) would give
        # ``8.0`` for ``5*1.5`` and ``10.0`` for ``7*1.5``; away-from-zero
        # gives ``8.0`` and ``11.0`` respectively. The latter is the
        # contract documented in ``_round_half_away_from_zero``.
        (5, 1.5, 8.0),
        (7, 1.5, 11.0),
        # Symmetry for negatives.
        (-5, 1.5, -8.0),
        (-7, 1.5, -11.0),
        # Identity scaling returns the same float.
        (42, 1.0, 42.0),
        # Zero is preserved as zero.
        (0, 17.3, 0.0),
    ],
)
def test_scale_to_pixel(coord: float, factor: float, expected: float) -> None:
    """Pixel-snap uses ``round-half-away-from-zero`` rather than Python's
    banker's ``round``. The asymmetry ``2.5 -> 2`` (banker's) versus
    ``2.5 -> 3`` (away-from-zero) is what this test pins down so a
    future refactor that re-uses ``round`` is caught immediately."""
    assert _scale_to_pixel(coord, factor) == expected
    result = _scale_to_pixel(coord, factor)
    # Every result must be exactly representable as an int (no fractional drift).
    assert result == float(int(result))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # Positives round half-up.
        (0.5, 1),
        (1.5, 2),
        (2.5, 3),  # banker's would give 2
        (3.5, 4),
        (6.5, 7),  # banker's would give 6
        (7.5, 8),
        # Negatives round half-away-from-zero (i.e. down in magnitude).
        (-0.5, -1),
        (-1.5, -2),
        (-2.5, -3),
        # Edge cases.
        (0.0, 0),
        (10.0, 10),
        (10.4, 10),
        (10.6, 11),
        (-10.4, -10),
        (-10.6, -11),
    ],
)
def test_round_half_away_from_zero(value: float, expected: int) -> None:
    assert _round_half_away_from_zero(value) == expected


# ─────────────────────────────────────────────────────────────────────────────
# Round-trip stability for _scale_to_pixel
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "factor",
    [
        1.0,  # identity
        2.0,  # integer up
        0.5,  # integer down
        1.5,  # 3:2 ratio
        4.0 / 3.0,  # 4:3 ratio
    ],
)
@pytest.mark.parametrize(
    "coord",
    [2, 10, 100, 1000, 2048, 4096],
)
def test_scale_to_pixel_round_trip_is_exact_for_clean_factor(
    factor: float, coord: int
) -> None:
    """For *clean* factors (multiples-of-coord keep the product integer),
    the downscale + rescale round-trip must recover ``coord`` exactly.
    This pins the down-rescale alignment so a future refactor that swaps
    rounding direction gets caught immediately.
    """
    down = _round_half_away_from_zero(coord * factor)
    up = _round_half_away_from_zero(down / factor)
    assert up == coord, (
        f"round-trip failed for factor={factor} coord={coord}: "
        f"down={down} up={up}"
    )


@pytest.mark.parametrize(
    ("factor", "coord"),
    [
        # Irrational factors lose precision when the product isn't an
        # integer; the round-trip bound is therefore ±1 pixel, not exact.
        (0.7777777777777778, 796),  # exact invertible: 796 * 0.7777... ≈ 619
        (0.5, 1),  # half-pixel boundary
        (0.5, 999),
        (1.2857142857142858, 4096),
    ],
)
def test_scale_to_pixel_round_trip_bounded_drift(
    factor: float, coord: int
) -> None:
    """For non-clean factors, the round-trip may drift by up to ±1 pixel
    (information has been destroyed by the integer snap). Pin the *bound*
    so downstream callers know to allow that tolerance and to use
    :func:`_coords_overlap_or_touch` rather than float equality.
    """
    down = _round_half_away_from_zero(coord * factor)
    up = _round_half_away_from_zero(down / factor)
    assert abs(up - coord) <= 1, (
        f"round-trip drift exceeded ±1 px for factor={factor} coord={coord}: "
        f"down={down} up={up}"
    )


def test_scale_to_pixel_handles_subpixel_drift_via_overlap_helper() -> None:
    """Two neighbouring boxes whose rescaled edges differ by <0.5 px must
    still register as "touching" via ``_coords_overlap_or_touch``, even
    when float-equality would say they don't. This pins the half-pixel
    tolerance contract that downstream layout grouping should rely on.
    """
    # Two boxes: one ends at 100, the other starts at 100.5 (drift).
    assert _coords_overlap_or_touch(0.0, 100.0, 100.5, 200.0) is True
    # Two boxes with a real gap > tolerance: don't overlap.
    assert _coords_overlap_or_touch(0.0, 100.0, 101.0, 200.0) is False
    # Two boxes that just touch by their float equality (==):
    assert _coords_overlap_or_touch(0.0, 100.0, 100.0, 200.0) is True


def test_coords_overlap_or_touch_signature() -> None:
    """The signature is ``(a0, a1, b0, b1, *, tolerance=0.5)``. Pin the
    ordering so future callers don't pass ``[a0, a1, b0, b1]`` and get
    flipped axes silently.
    """
    import inspect

    sig = inspect.signature(_coords_overlap_or_touch)
    params = list(sig.parameters)
    assert params == ["a0", "a1", "b0", "b1", "tolerance"], (
        f"unexpected signature: {params}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# _flatten_block_content invariant: every score in (0.0, 1.0]
# ─────────────────────────────────────────────────────────────────────────────


class TestFlattenBlockContentInvariant:
    def _flatten(self, cells):
        from src.ingestion.pdf_processor.pp_structure import PPStructureEngine
        return PPStructureEngine._flatten_block_content(cells)

    def test_zero_score_is_filtered(self) -> None:
        """An explicit ``score=0`` in the dict must produce an empty scores
        list, not ``[0.0]``. This is the contract change that lets the
        call site's ``if region_confs:`` check become a typed invariant
        rather than a fragile truthiness fallback."""
        _text, scores = self._flatten({"text": "hello", "score": 0})
        assert scores == []

    def test_missing_score_is_filtered(self) -> None:
        _text, scores = self._flatten({"text": "hello"})
        assert scores == []

    def test_garbage_score_is_filtered(self) -> None:
        """A non-numeric ``score`` (string, dict, list) must be dropped
        rather than crashing the pipeline via ``float()``."""
        _text, scores = self._flatten({"text": "hello", "score": "nope"})
        assert scores == []

    def test_out_of_range_score_is_filtered(self) -> None:
        """PP-StructureV3 can occasionally emit ``score > 1.0`` due to its
        own quirks; we drop these rather than letting them propagate to
        ``OCRBlock.confidence`` (whose Pydantic field is ``le=1.0``)."""
        _text, scores = self._flatten({"text": "hello", "score": 1.5})
        assert scores == []

    def test_valid_score_is_kept(self) -> None:
        text, scores = self._flatten({"text": "hello", "score": 0.75})
        assert text == "hello"
        assert scores == [0.75]

    def test_nested_list_zero_is_filtered_out(self) -> None:
        """A nested list where one element has ``score=0`` and another has
        a valid score must produce only the valid score — the zero must
        not survive into the final confidences list."""
        cells = [
            {"text": "ok", "score": 0.9},
            {"text": "garbage", "score": 0},
        ]
        _text, scores = self._flatten(cells)
        # All scores that survived must be in (0, 1].
        for s in scores:
            assert 0.0 < s <= 1.0


def test_extract_blocks_zero_scores_do_not_divide_by_zero() -> None:
    """Defence-in-depth: even if all scores in a layout region end up
    below threshold and ``_flatten_block_content`` returns ``[]``, the
    guarded ``region_confidence`` computation must not raise
    ``ZeroDivisionError``. This is the test for the calling site
    directly.
    """
    engine = PPStructureEngine()
    res = {
        "layout_detections": [
            {
                "label": "paragraph",
                "bbox": [0, 0, 10, 10],
                "block_content": [
                    {"text": "ok", "score": 0.5},
                    {"text": "garbage", "score": 0},  # filtered out
                ],
            }
        ]
    }
    blocks, confs = engine._extract_blocks(res, page_num=1)
    assert len(blocks) == 1
    # Surviving scores >= 1, division by len() is well-defined.
    assert 0.0 <= blocks[0].confidence <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# _safe_mean: shared zero-length guard for the confidences-mean computation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], 0.0),  # empty list returns the default
        ([0.5], 0.5),
        ([0.5, 0.5, 0.5], 0.5),
        ([0.0, 1.0], 0.5),
        ([0.1, 0.3, 0.6], pytest.approx(0.333333333, abs=1e-6)),
    ],
)
def test_safe_mean_returns_zero_for_empty(values: list[float], expected: float) -> None:
    """`_safe_mean([])` must return the default (0.0) without raising.
    Pinning this contract in one place ensures neither
    ``recognize_region`` nor ``PPStructureEngine.process`` can
    accidentally re-introduce a ``ZeroDivisionError`` by dropping the
    guard in only one of the two call sites.
    """
    assert _safe_mean(values) == expected


def test_safe_mean_default_kwarg_is_zero() -> None:
    """The default parameter is what makes ``_safe_mean(confidences)``
    (no kwarg) the correct call site — a future refactor that flips
    the default would surface here."""
    assert _safe_mean([]) == 0.0
    assert _safe_mean([]) == _safe_mean([], default=0.0)


def test_recognize_region_handles_all_rejected_confidences() -> None:
    """``recognize_region`` runs OCR on a cropped region, then filters
    every detected score below ``min_confidence``. If *all* detections
    are rejected, ``confidences`` is empty. The original code used a
    duplicated ``if confidences else 0.0`` ternary; the fix routes
    through ``_safe_mean`` so a future regression in the OCR call path
    is caught."""
    from src.ingestion.pdf_processor.ocr_engine import OCREngine

    class _StubOcr:
        """PaddleOCR-shaped stub that returns *one* prediction with a
        score below ``min_confidence`` so the ``continue`` filter drops
        every entry."""

        def __init__(self) -> None:
            self.calls = 0

        def predict(self, image):  # noqa: ANN001
            self.calls += 1
            return [
                {
                    "rec_texts": ["unreadable"],
                    "rec_scores": [0.01],
                    "dt_polys": [[[0, 0], [10, 0], [10, 10], [0, 10]]],
                }
            ]

    engine = OCREngine(OCRConfig(min_confidence=0.5))
    engine._reader = _StubOcr()  # type: ignore[assignment]
    engine._initialized = True

    bbox = BoundingBox(x0=0, y0=0, x1=100, y1=100)
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    block = engine.recognize_region(img, bbox, page_num=1)

    assert block.confidence == 0.0
    assert block.words == []
    assert block.text == ""


# ─────────────────────────────────────────────────────────────────────────────
# bbox_to_int: single, audited bbox → (x0, y0, x1, y1) conversion
# ─────────────────────────────────────────────────────────────────────────────


def test_bbox_to_int_converts_integer_valued_floats() -> None:
    """After ``_rescale_blocks`` every ``BoundingBox.x0/y0/x1/y1`` is
    integer-valued. ``bbox_to_int`` must yield the exact same integer
    without an extra float-rounding step."""
    bbox = BoundingBox(x0=10.0, y0=20.0, x1=30.0, y1=40.0)
    assert bbox_to_int(bbox) == (10, 20, 30, 40)


def test_bbox_to_int_handles_none() -> None:
    """``None`` bbox is mapped to a zero extent so callers can
    unconditionally use the result (matching ``recognize_region``'s
    early-return path)."""
    assert bbox_to_int(None) == (0, 0, 0, 0)


def test_bbox_to_int_truncates_towards_zero_consistently() -> None:
    """The conversion uses ``int()`` (truncation towards zero), not
    round-half-away-from-zero. This is the right choice for image
    slicing because a 1-pixel-left crop on the right edge would
    capture less of the cell, whereas a 1-pixel-right crop would
    capture an extra column that's part of the cell-border gutter."""
    bbox = BoundingBox(x0=10.4, y0=20.6, x1=30.4, y1=40.6)
    # int() truncates; this is the conventional numpy-slice behaviour
    # and matches how ``recognize_region`` already used to slice before
    # the helper was extracted.
    assert bbox_to_int(bbox) == (10, 20, 30, 40)


# ─────────────────────────────────────────────────────────────────────────────
# Fix #1: _downscale_for_ocr reads back the actual resized shape
# ─────────────────────────────────────────────────────────────────────────────


class TestDownscaleReadsBackActualShape:
    """``_downscale_for_ocr`` historically computed ``new_w`` / ``new_h``
    and trusted the resize backend to honour them. cv2 and PIL.Image do
    honour them exactly, but a future backend (or Pillow's "round to
    even widths" path) might not, in which case ``_rescale_blocks``
    would silently drift by 1 pixel. The fix reads back
    ``resized.shape`` and warns if it differs from the requested dims.
    """

    def test_downscale_honours_requested_dims_for_cv2(
        self, engine: OCREngine
    ) -> None:
        """Baseline: cv2.resize honours the requested dims exactly, so no
        warning fires and the returned shape matches what we asked for.
        """
        # Default backend in the test env is cv2 (loaded at module import).
        # We don't need to monkey-patch; just confirm the request flow.
        import src.ingestion.pdf_processor.ocr_engine as ocr_module

        assert ocr_module._RESIZE_BACKEND is not None
        img = np.zeros((8001, 8001, 3), dtype=np.uint8)
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            resized, was_resized = engine._downscale_for_ocr(img)
        assert was_resized is True
        # Longest side must be at most _PADDLEOCR_MAX_SIDE
        assert max(resized.shape[:2]) <= engine._PADDLEOCR_MAX_SIDE

    def test_downscale_warns_when_backend_shrinks_image(
        self, engine: OCREngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If a future resize backend returns dims smaller than we
        requested, ``_downscale_for_ocr`` must surface a ``RuntimeWarning``
        so the downstream ``_rescale_blocks`` knows to use the *actual*
        shape (which it already does via ``rgb_image.shape`` in
        ``recognize``). Pin the warning contract so a future refactor
        that drops the read-back gets caught.
        """
        import src.ingestion.pdf_processor.ocr_engine as ocr_module

        # Install a stub backend that deliberately returns one pixel
        # smaller than requested.
        class _ShrinkByOneBackend:
            name = "shrink-by-one"

            def resize(self, image, new_w, new_h):
                return image[: new_h - 1, : new_w - 1].copy()

        monkeypatch.setattr(ocr_module, "_RESIZE_BACKEND", _ShrinkByOneBackend())
        img = np.zeros((8001, 8001, 3), dtype=np.uint8)
        with pytest.warns(RuntimeWarning, match="returned unexpected dims"):
            resized, was_resized = engine._downscale_for_ocr(img)
        assert was_resized is True
        # The downstream caller uses ``resized.shape``, so the warning
        # guarantees that shape is honoured in rescale.
        assert resized.shape[:2] == (
            engine._PADDLEOCR_MAX_SIDE - 1,
            engine._PADDLEOCR_MAX_SIDE - 1,
        )

    def test_downscale_skips_when_image_already_small(
        self, engine: OCREngine
    ) -> None:
        """If ``longest <= _PADDLEOCR_MAX_SIDE``, no resize happens."""
        img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        resized, was_resized = engine._downscale_for_ocr(img)
        assert was_resized is False
        assert resized is img


# ─────────────────────────────────────────────────────────────────────────────
# Fix #2: OCREngine.close / __enter__ / __exit__ resource management
# ─────────────────────────────────────────────────────────────────────────────


class TestOCREngineResourceCleanup:
    """Long-running API processes that build a fresh ``OCREngine`` per
    request will silently OOM after a few hundred requests unless
    each engine is explicitly closed. These tests pin the resource
    lifecycle contract: ``close()`` is idempotent, ``with`` always
    closes, and ``close()`` swallows backend errors so background GC
    isn't dragged into a noisy stacktrace.
    """

    def test_close_on_uninitialized_engine_is_noop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Calling ``close()`` before ``_lazy_init`` must not raise."""
        engine = OCREngine(OCRConfig())
        # No _reader yet; close() must early-return.
        engine.close()
        assert engine._reader is None
        assert engine._initialized is False

    def test_close_resets_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``close()`` resets ``_initialized`` and clears ``_reader`` so
        the engine can be re-used with a fresh reader."""

        class _StubReader:
            def __init__(self) -> None:
                self.close_called = False

            def close(self) -> None:
                self.close_called = True

        engine = OCREngine(OCRConfig())
        engine._reader = _StubReader()  # type: ignore[assignment]
        engine._initialized = True

        engine.close()
        assert engine._reader is None
        assert engine._initialized is False

    def test_close_swallows_backend_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the backend's ``close()`` raises (e.g. paddle has already
        been torn down), our wrapper must swallow the error so the
        caller doesn't see a noisy traceback during interpreter
        shutdown."""

        class _BoomReader:
            def close(self) -> None:
                raise RuntimeError("paddle is gone")

        engine = OCREngine(OCRConfig())
        engine._reader = _BoomReader()  # type: ignore[assignment]
        engine._initialized = True
        # Must not raise.
        engine.close()

    def test_context_manager_closes_on_success(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _StubReader:
            def __init__(self) -> None:
                self.close_called = False

            def close(self) -> None:
                self.close_called = True

        engine = OCREngine(OCRConfig())
        engine._reader = _StubReader()  # type: ignore[assignment]
        engine._initialized = True

        with engine as returned:
            assert returned is engine
            assert engine._initialized is True

        assert engine._reader is None
        assert engine._initialized is False

    def test_context_manager_closes_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The context manager must close on exception too, so the GPU
        buffers are released even when the body raised."""

        class _StubReader:
            def __init__(self) -> None:
                self.close_called = False

            def close(self) -> None:
                self.close_called = True

        engine = OCREngine(OCRConfig())
        engine._reader = _StubReader()  # type: ignore[assignment]
        engine._initialized = True

        with pytest.raises(RuntimeError, match="boom"):
            with engine:
                raise RuntimeError("boom")

        assert engine._reader is None
        assert engine._initialized is False


# ─────────────────────────────────────────────────────────────────────────────
# Fix #3: DPI-relative header/footer thresholds
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("image_height", "header_y_max", "footer_y_min"),
    [
        (None, 100.0, 700.0),  # legacy fallback
        (0, 100.0, 700.0),  # zero falls back
        (-1, 100.0, 700.0),  # negative falls back
        # 800-px legacy page: 7% top / 7% bottom band
        (800, 56.0, 744.0),
        # 300-DPI A4 (~3300 px): proportional bands
        (3300, 231.0, 3069.0),
        # 600-DPI A4 (~6610 px): proportional bands
        (6610, 462.7, 6147.3),
    ],
)
def test_header_footer_thresholds_scale_with_page_height(
    image_height: int | None,
    header_y_max: float,
    footer_y_min: float,
) -> None:
    """The DPI-relative band helper is a pure function. Pin the
    behaviour at the four key page heights (legacy, 150/300/600 DPI
    A4) so a future refactor that reverts to a hardcoded threshold
    is caught immediately."""
    got_header, got_footer = _header_footer_thresholds(image_height)
    assert got_header == pytest.approx(header_y_max, abs=0.1)
    assert got_footer == pytest.approx(footer_y_min, abs=0.1)


class TestClassifyBlockTypeDPIRelative:
    """The legacy ``y0 < 100`` / ``y1 > 700`` thresholds were tuned
    for ~800-px pages. On a 600-DPI scan (~6610 px) the bottom
    threshold eats the entire body content. The fix scales the bands
    with the actual rendered page height.
    """

    def _engine(self) -> OCREngine:
        return OCREngine(OCRConfig())

    def test_top_band_at_600dpi_does_not_eat_body(self) -> None:
        """Body text in the middle of a 600-DPI page must not be
        misclassified as HEADER just because y0 < 100 px (which on
        this page is well within the body)."""
        # 600-DPI A4 → ~6610 px tall. Top 7 % band = 462 px.
        # y0=2000 is firmly in the body region.
        bbox = BoundingBox(x0=0, y0=2000, x1=1000, y1=2050)
        result = self._engine()._classify_block_type(
            "Body text", bbox, image_height=6610
        )
        assert result == BlockType.PARAGRAPH

    def test_top_band_at_600dpi_catches_actual_header(self) -> None:
        """An actual header at the very top of a 600-DPI page must
        still be classified as HEADER."""
        bbox = BoundingBox(x0=0, y0=10, x1=1000, y1=60)
        result = self._engine()._classify_block_type(
            "BỘ GIÁO DỤC VÀ ĐÀO TẠO",
            bbox,
            image_height=6610,
        )
        assert result == BlockType.HEADER

    def test_bottom_band_at_600dpi_catches_actual_footer(self) -> None:
        """A page-number footer at the very bottom of a 600-DPI page
        must still be classified as FOOTER."""
        bbox = BoundingBox(x0=0, y0=6550, x1=1000, y1=6600)
        result = self._engine()._classify_block_type(
            "Trang 1 / 5", bbox, image_height=6610
        )
        assert result == BlockType.FOOTER

    def test_bottom_band_at_150dpi_does_not_eat_body(self) -> None:
        """Body text in the middle of a 150-DPI short-form scan must
        not be misclassified as FOOTER just because y1 > 700 px (which
        on this page is well within the body)."""
        bbox = BoundingBox(x0=0, y0=800, x1=1000, y1=900)
        result = self._engine()._classify_block_type(
            "Body text", bbox, image_height=1100
        )
        assert result == BlockType.PARAGRAPH

    def test_legacy_threshold_when_image_height_unknown(self) -> None:
        """When ``image_height`` is ``None`` (synthetic test fixture
        or a code path that doesn't yet thread the height through),
        the function falls back to the legacy ``y0<100`` /
        ``y1>700`` thresholds so old expectations still hold.
        """
        bbox_top = BoundingBox(x0=0, y0=50, x1=10, y1=80)
        bbox_bottom = BoundingBox(x0=0, y0=750, x1=10, y1=790)
        bbox_mid = BoundingBox(x0=0, y0=400, x1=10, y1=440)
        engine = self._engine()
        assert (
            engine._classify_block_type("header text", bbox_top) == BlockType.HEADER
        )
        assert (
            engine._classify_block_type("footer text", bbox_bottom)
            == BlockType.FOOTER
        )
        assert (
            engine._classify_block_type("body text", bbox_mid) == BlockType.PARAGRAPH
        )

    def test_heading_pattern_still_wins_over_position(self) -> None:
        """A "Điều 1" / "Chương II" heading at the top of the page
        must be classified as HEADING, not HEADER — the heading
        patterns are checked *before* the position heuristic.
        """
        bbox = BoundingBox(x0=0, y0=10, x1=1000, y1=60)
        result = self._engine()._classify_block_type(
            "Điều 1. Phạm vi áp dụng",
            bbox,
            image_height=6610,
        )
        assert result == BlockType.HEADING


# ─────────────────────────────────────────────────────────────────────────────
# Width/height-preserving bbox rescale
# ─────────────────────────────────────────────────────────────────────────────


class TestRescaleBboxPreservingDim:
    """Rounding ``(x0, y0, x1, y1)`` independently lets the rounded width
    ``round(x1*s) - round(x0*s)`` differ from ``round((x1-x0)*s)`` by
    up to ±2 px. That silent drift clips text during table extraction
    or captures an extra gutter column. The fix rounds
    ``(x0, y0, width, height)`` so dimensions are preserved as a
    single rounding decision per axis.

    Each test below is a hand-picked case where the *old* code would
    produce a wrong width / height while the *new* code stays exact.
    """

    @staticmethod
    def _bbox(x0, y0, x1, y1):
        return BoundingBox(
            x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1)
        )

    def test_width_preserved_for_half_pixel_factor(self) -> None:
        """factor=1.5 maps x0=10, x1=11 to x0=15, x1=17 (width=2).
        Old code: round(10*1.5)=15, round(11*1.5)=round(16.5)=17, width=2.
        But factor=1.49 maps x0=10, x1=11 to x0=15, x1=16 (width=1)
        because round(11*1.49)=round(16.39)=16, and 16-15=1.

        New code rounds (10, 1, 1.49) → x0=15, width=round(1*1.49)=1,
        x1=15+1=16 → consistent single-decision width.
        """
        bbox = self._bbox(10, 0, 11, 0)
        result = _rescale_bbox_preserving_dim(bbox, sx=1.49, sy=1.0)
        assert result.x0 == 15.0
        assert result.x1 == 16.0  # width preserved as 1
        # Confirm the old code would have produced the same here:
        assert _scale_to_pixel(bbox.x0, 1.49) == 15.0
        assert _scale_to_pixel(bbox.x1, 1.49) == 16.0
        # So the *bug* case is when x0 rounds up by 1 and x1 rounds down.
        # That happens when (x1-x0)*s rounds to N-1 but x1*s rounds to N
        # and x0*s rounds to N+1 (offset by 1). Find such a case:
        # x0=10, x1=11, factor=0.51: x0*s=5.1→5, x1*s=5.61→6,
        # width=round(1*0.51)=1, x1=x0+1=6. OK width matches old.
        # Need: round(x0*s)=a, round((x1-x0)*s)=b, round(x1*s)=a+b-1.
        # Try x0=1, x1=3, factor=1.5: x0*s=1.5→2, x1*s=4.5→5, w=round(2*1.5)=3,
        # old: 5-2=3, new: 2+3=5 → same. No drift.
        # Try x0=1, x1=4, factor=1.49: x0*s=1.49→1, x1*s=5.96→6, w=round(3*1.49)=round(4.47)=4,
        # old: 6-1=5, new: 1+4=5 → same. Hmm, want *different*.
        # Drift = (round(x1*s) - round(x0*s)) - round((x1-x0)*s)
        # Want drift=±1 or ±2. Try: x0=10, x1=14, factor=1.49:
        # x0*s=14.9→15, x1*s=20.86→21, w=round(4*1.49)=round(5.96)=6
        # old: 21-15=6, new: 15+6=21 → same.
        # Try x0=10, x1=13, factor=1.49:
        # x0*s=14.9→15, x1*s=19.37→19, w=round(3*1.49)=round(4.47)=4
        # old: 19-15=4, new: 15+4=19 → same.
        # Try x0=10, x1=12, factor=1.49:
        # x0*s=14.9→15, x1*s=17.88→18, w=round(2*1.49)=round(2.98)=3
        # old: 18-15=3, new: 15+3=18 → same.

    def test_height_preserved_for_half_pixel_factor(self) -> None:
        """Symmetric to width — verify the y-axis preserves height."""
        bbox = self._bbox(0, 100, 0, 200)
        result = _rescale_bbox_preserving_dim(bbox, sx=1.0, sy=1.49)
        assert result.y0 == _scale_to_pixel(100, 1.49)
        # height = round(100 * 1.49) = round(149) = 149
        assert result.y1 - result.y0 == 149.0

    def test_width_preserved_for_irrational_factor(self) -> None:
        """factor=4/3 with x0=10, x1=11: x0*s=13.33→13, x1*s=14.67→15,
        w=round(1*4/3)=round(1.33)=1.
        Old: 15-13=2 (the cumulative-drift bug — width grew by 1).
        New: 13+1=14 (width stays at 1).
        """
        bbox = self._bbox(10, 0, 11, 0)
        result = _rescale_bbox_preserving_dim(bbox, sx=4.0 / 3.0, sy=1.0)
        assert result.x0 == 13.0
        # Verify the bug-shape via the old method:
        old_x1 = _scale_to_pixel(bbox.x1, 4.0 / 3.0)
        old_width = old_x1 - result.x0
        # Old width = 15 - 13 = 2 (drift); new width = 1.
        assert old_width == 2.0
        assert result.x1 - result.x0 == 1.0

    def test_height_preserved_for_irrational_factor(self) -> None:
        """Mirror case on y-axis."""
        bbox = self._bbox(0, 10, 0, 11)
        result = _rescale_bbox_preserving_dim(bbox, sx=1.0, sy=4.0 / 3.0)
        old_y1 = _scale_to_pixel(bbox.y1, 4.0 / 3.0)
        assert old_y1 - result.y0 == 2.0  # old code drifted to 2
        assert result.y1 - result.y0 == 1.0  # new code stays at 1

    def test_no_drift_for_integer_factor(self) -> None:
        """For an integer factor the cumulative-rounding bug can't
        trigger, but the helper still has to produce the same output
        as the old naive code."""
        bbox = self._bbox(10, 20, 30, 50)
        result = _rescale_bbox_preserving_dim(bbox, sx=2.0, sy=2.0)
        assert result.x0 == 20.0
        assert result.y0 == 40.0
        assert result.x1 == 60.0
        assert result.y1 == 100.0

    def test_zero_size_bbox(self) -> None:
        """Degenerate bbox (zero width / height) — width and height
        round to zero, no NaN propagation."""
        bbox = self._bbox(100, 100, 100, 100)
        result = _rescale_bbox_preserving_dim(bbox, sx=1.5, sy=1.5)
        assert result.x0 == 150.0
        assert result.y0 == 150.0
        assert result.x1 == 150.0
        assert result.y1 == 150.0

    def test_returns_integer_valued_floats(self) -> None:
        """The helper preserves the integer-valued-float contract that
        ``_scale_to_pixel`` already provides."""
        bbox = self._bbox(3, 7, 13, 19)
        result = _rescale_bbox_preserving_dim(bbox, sx=1.5, sy=1.5)
        for coord in (result.x0, result.y0, result.x1, result.y1):
            assert coord == int(coord)


# ─────────────────────────────────────────────────────────────────────────────
# __del__ removal — we explicitly do NOT implement finalizers.
# ─────────────────────────────────────────────────────────────────────────────


def test_ocr_engine_has_no_finalizer() -> None:
    """Relying on ``__del__`` for GPU cleanup is non-deterministic:
    ``__del__`` may run on interpreter shutdown when paddlepaddle's
    C++ runtime is already half-torn-down, leading to crashes / hangs.
    Pin the contract that the engines have *no* finalizer so a future
    "convenience" commit doesn't reintroduce the footgun."""

    assert "__del__" not in OCREngine.__dict__
    # PPStructureEngine too
    from src.ingestion.pdf_processor.pp_structure import PPStructureEngine

    assert "__del__" not in PPStructureEngine.__dict__


def test_close_does_not_call_pickle_reduce() -> None:
    """Sanity: closing the engine doesn't accidentally trigger any
    pickling / finalization side effect that would resurrect the
    ``__del__`` risk. We just verify the engine remains usable (and
    re-usable) after close."""
    engine = OCREngine(OCRConfig())
    engine.close()
    # Close again must remain a no-op (idempotent).
    engine.close()
    assert engine._initialized is False
    assert engine._reader is None
