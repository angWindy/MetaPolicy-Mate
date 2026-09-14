"""OCR Engine for PDF scan pages — RapidOCR + PP-OCRv6 Vietnamese.

Single-engine architecture: RapidOCR ONNX with a Vietnamese-tuned
recognition model (PP-OCRv6_mobile_rec) plus the bundled detection and
classification models. No factory abstraction, no fallback engine —
the pipeline calls :class:`OCREngine` directly.

Configuration notes (validated in ``data/ocr/outputs/REPORT.md``):

* Recognition: ``data/ocr/outputs/onnx_models/rec_vi/inference.onnx``
  (PP-OCRv6_mobile_rec, 73 MB) + ``dict.txt`` (18 708 multilingual
  characters including the Vietnamese ``Đ`` and ``ê``).
* Detection + classification: bundled defaults from
  ``rapidocr_onnxruntime`` (ch_PP-OCRv4_det + ch_ppocr_mobile_v2.0_cls).
* DPI: 200 with Otsu binary preprocessing for body pages; 600 for the
  cover page (handled by the pipeline).
* Score threshold: 0.5.

The public surface (``recognize`` / ``recognize_region`` /
``warmup`` / ``close``) is preserved byte-for-byte so the calling
pipeline does not change. The hybrid text-extract-first gate is
implemented in the pipeline, not here.

Per docs/pdf_processing_pipeline.md Section 6:

* Vietnamese diacritic preservation is required (see
  ``.cursor/plans/ocr_migration_plan_(with_deep_vietnamese_audit)_*.md``).
* Layout awareness (paragraph/heading regions) and table cell OCR
  (per-cell processing) remain pipeline responsibilities.
"""

from __future__ import annotations

import json
import math
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from src.ingestion.pdf_processor.schemas import (
    BlockType,
    BoundingBox,
    OCRBlock,
    OCRResult,
    OCRWord,
    PageType,
)
from src.ingestion.pdf_processor.vn_diacritic_restore import (
    OcrArtifactCleaner,
    VNDiacriticRestorer,
    get_default_restorer,
)


# Default location of the Vietnamese recognition model. The
# ``install_rec_onnx.sh`` script copies ``data/ocr/outputs/onnx_models/rec_vi/``
# here at deploy time. The dict lives next to it.
DEFAULT_VI_MODEL_DIRNAME = "rec_vi"
DEFAULT_MODELS_ROOT = Path("ocr_models")


@dataclass
class OCRConfig:
    """Configuration for OCR engine."""

    # RapidOCR runtime — DPI / preprocessing knobs the pipeline forwards
    # to the engine. The recognizer score threshold is enforced both
    # inside RapidOCR (``text_score``) and on the post-filter here so
    # downstream consumers see only confident blocks.
    body_dpi: int = 200
    cover_dpi: int = 600
    text_score: float = 0.5  # RapidOCR ``text_score`` parameter
    use_det: bool = True
    use_cls: bool = True

    # Vietnamese model location. Relative paths are resolved against the
    # project root; pass an absolute path to use a sandboxed install.
    models_dir: Path = DEFAULT_MODELS_ROOT
    vi_model_subdir: str = DEFAULT_VI_MODEL_DIRNAME

    # The parser pipeline still constructs OCRConfig from RAGSettings fields
    # such as ``languages=["vi", "en"]`` so we expose the same surface here
    # for back-compat. RapidOCR + PP-OCRv6 Vietnamese ONNX handles both
    # languages natively, so ``languages`` is informational only.
    languages: list[str] = field(default_factory=lambda: ["vi", "en"])

    # Confidence thresholds (consumed by the pipeline + recognizer)
    min_confidence: float = 0.5
    low_confidence_threshold: float = 0.7
    block_confidence_threshold: float = 0.6

    # Layout detection
    detect_tables: bool = True
    detect_headings: bool = True

    # Text processing
    paragraph_max_line_gap: int = 10
    merge_broken_words: bool = True

    # Legacy compatibility — kept so old call sites that read
    # ``config.gpu`` / ``config.lang`` do not break. RapidOCR does not
    # use them; they are accepted and ignored.
    lang: str = "vi"
    gpu: bool = False
    enable_mkldnn: bool = False
    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False
    ocr_version: str | None = None
    text_det_limit_side_len: int = 1536
    text_rec_score_thresh: float = 0.5
    text_recognition_batch_size: int = 4
    batch_size: int = 4
    workers: int = 4

    @property
    def resolved_lang(self) -> str:
        """Pick the canonical language code from ``languages``.

        Informational only — RapidOCR + PP-OCRv6 Vietnamese ONNX uses a
        bundled multilingual model and does not accept a language code
        as a runtime parameter.
        """
        for code in self.languages:
            if code.lower().startswith("vi"):
                return "vi"
        return self.lang or "en"


class OCREngine:
    """OCR Engine using RapidOCR + PP-OCRv6 Vietnamese ONNX.

    Single-engine architecture: the constructor eagerly loads the
    Vietnamese recognition model and the bundled default detection +
    classification models. Long-running API processes should pair this
    engine with a context manager (``with OCREngine(...) as engine:``)
    so the ONNX Runtime sessions are released on exit.

    Usage::

        with OCREngine(config=OCRConfig()) as engine:
            result = engine.recognize(image, page_num=1)
    """

    name: str = "rapidocr_vi"

    # Cap the longest side at 4000 px so RapidOCR's internal
    # preprocessing does not run away on high-DPI scans.
    _RAPIDOCR_MAX_SIDE = 4000

    def __init__(self, config: OCRConfig | None = None):
        self.config = config or OCRConfig()
        self._engine: Any = None
        self._initialized = False
        # Lazy-loaded Vietnamese diacritic restorer. Looks up every
        # stripped token emitted by PP-OCRv6 against the corpus wordlist
        # built by ``scripts/ocr/build_vn_wordlist.py``. No-op if the
        # wordlist is missing.
        self._vn_restorer: VNDiacriticRestorer | None = None
        # Sibling OCR-artifact cleaner. Always available (stateless,
        # no wordlist), runs before the diacritic restorer so heading
        # markers (``Điều``, ``Chương``, ...) reach the restorer in
        # canonical form instead of the scrambled (``ĐiuẢ``,
        # ``ChuưongẢ``) variants PP-OCRv6 tends to emit on scan pages.
        self._ocr_cleaner: OcrArtifactCleaner = OcrArtifactCleaner()

    # ------------------------------------------------------------------ #
    # Model loader
    # ------------------------------------------------------------------ #

    def _resolve_model_dir(self) -> Path:
        """Resolve the Vietnamese model directory.

        Search order:
        1. ``<models_dir>/<vi_model_subdir>`` as configured (default
           ``./ocr_models/rec_vi``).
        2. ``data/ocr/outputs/onnx_models/rec_vi`` — the development
           workspace location used during model bring-up.

        Returns the first existing directory. Raises an actionable error
        if neither is present.
        """
        candidates: list[Path] = []
        primary = self.config.models_dir / self.config.vi_model_subdir
        candidates.append(primary)
        candidates.append(
            Path("data/ocr/outputs/onnx_models") / self.config.vi_model_subdir
        )
        for cand in candidates:
            if cand.is_dir():
                return cand
        raise RuntimeError(
            "RapidOCR Vietnamese model directory not found. "
            f"Tried: {[str(c) for c in candidates]}. "
            "Run scripts/ocr/install_rec_onnx.sh to copy the model "
            "from data/ocr/outputs/onnx_models/rec_vi/ into ./ocr_models/rec_vi/. "
            "Or pip install rapidocr-onnxruntime[opencv]."
        )

    def _lazy_init(self) -> None:
        """Lazy initialization of the RapidOCR engine + Vietnamese model.

        Failing fast here means a missing model is surfaced at the
        first ``recognize()`` call rather than at container start, but
        :meth:`warmup` can be used to surface it earlier.
        """
        if self._initialized:
            return

        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ImportError(
                "rapidocr_onnxruntime not installed. "
                "Install with: pip install rapidocr-onnxruntime[opencv]"
            ) from exc

        model_dir = self._resolve_model_dir()
        onnx_path = model_dir / "inference.onnx"
        dict_path = model_dir / "dict.txt"

        missing = [
            str(p) for p in (onnx_path, dict_path) if not p.exists()
        ]
        if missing:
            raise RuntimeError(
                f"RapidOCR Vietnamese model files missing in {model_dir}: "
                f"{', '.join(missing)}. "
                "Run scripts/ocr/install_rec_onnx.sh."
            )

        # RapidOCR defaults (det + cls ONNX) live inside the
        # ``rapidocr_onnxruntime`` package; passing only the rec model
        # path makes it pick the bundled det/cls.
        self._engine = RapidOCR(
            rec_model_path=str(onnx_path),
            rec_keys_path=str(dict_path),
            text_score=self.config.text_score,
            use_det=self.config.use_det,
            use_cls=self.config.use_cls,
        )
        self._model_dir = model_dir
        self._initialized = True

    def warmup(self) -> None:
        """Pre-load the model so the first ``recognize()`` is hot.

        The pipeline calls ``warmup()`` once at startup so a missing
        model surfaces as a service start-up error instead of a 500 on
        the first OCR request.
        """
        self._lazy_init()

    def close(self) -> None:
        """Release the RapidOCR engine (closes the ONNX Runtime session)."""
        if not self._initialized:
            return
        engine = getattr(self, "_engine", None)
        if engine is not None:
            close = getattr(engine, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # noqa: BLE001
                    warnings.warn(
                        f"RapidOCR close failed: {exc}", RuntimeWarning, stacklevel=2
                    )
        self._engine = None
        self._initialized = False

    def __enter__(self) -> OCREngine:
        self.warmup()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Public API — preserves the legacy ``recognize``/``recognize_region``
    # contract so the calling pipeline does not change.
    # ------------------------------------------------------------------ #

    def recognize(
        self,
        image: np.ndarray,
        page_num: int = 1,
        preprocessed: bool = True,
    ) -> OCRResult:
        """Recognize text from a page image via RapidOCR ONNX.

        Args:
            image: Input image (H, W, C) in RGB or BGR.
            page_num: Page number for metadata.
            preprocessed: Whether the image is already preprocessed
                (binary threshold etc.). RapidOCR accepts both;
                preprocessed images are passed through verbatim.

        Returns:
            OCRResult with recognized blocks and metadata.
        """
        if not self._initialized:
            self._lazy_init()

        rgb_image = self._to_rgb(image)
        rgb_image, was_resized = self._downscale_for_ocr(rgb_image)

        # RapidOCR returns ``(result, elapse)`` where ``result`` is
        # either ``None`` (no text detected) or a list of
        # ``[box, text, score]`` triples.
        result, _elapse = self._engine(rgb_image)
        blocks = self._process_raw_results(
            result, page_num, image_height=rgb_image.shape[0]
        )
        if was_resized:
            blocks = self._rescale_blocks(blocks, rgb_image.shape, image.shape)
        # Apply Vietnamese diacritic restoration (data-driven wordlist
        # lookup). Restores chars the CTCDecoder dropped on the wire.
        blocks = self._restore_diacritics_blocks(blocks)
        avg_confidence = self._calculate_average_confidence(blocks)
        raw_text = "\n".join(b.text for b in blocks)
        needs_review = self._check_needs_review(blocks)
        warnings_list = self._generate_warnings(blocks)

        return OCRResult(
            page=page_num,
            page_type=PageType.SCAN,
            blocks=blocks,
            tables=[],
            raw_text=raw_text,
            average_confidence=avg_confidence,
            needs_review=needs_review,
            warnings=warnings_list,
        )

    def recognize_region(
        self,
        image: np.ndarray,
        bbox: BoundingBox,
        page_num: int = 1,
    ) -> OCRBlock:
        """Recognize text from a specific region via RapidOCR.

        Useful for:
        - Table cell OCR
        - Targeted OCR after layout detection
        - VLM review crop OCR
        """
        if not self._initialized:
            self._lazy_init()

        x0, y0, x1, y1 = bbox_to_int(bbox)
        region = image[y0:y1, x0:x1]
        if region.size == 0:
            return OCRBlock(
                block_type=BlockType.PARAGRAPH,
                text="",
                bbox=bbox,
                page=page_num,
                confidence=0.0,
            )
        region = self._to_rgb(region)

        result, _elapse = self._engine(region)

        words: list[OCRWord] = []
        full_text_parts: list[str] = []
        confidences: list[float] = []

        for entry in self._iter_rapidocr_entries(result):
            text = entry["text"]
            score = entry["score"]
            if score < self.config.min_confidence:
                continue

            cell_bbox = self._coords_to_bbox(entry["polys"])
            words.append(OCRWord(text=text, bbox=cell_bbox, confidence=score))
            full_text_parts.append(text)
            confidences.append(score)

        avg_conf = _safe_mean(confidences)

        # Apply Vietnamese diacritic restoration to the merged text.
        # Two stages: OCR-artifact cleaner first (stateless, always
        # available), then wordlist restorer (skip if wordlist missing).
        joined = " ".join(full_text_parts)
        cleaned = self._ocr_cleaner.clean(joined)
        restorer = self._get_vn_restorer()
        if restorer is not None and full_text_parts:
            restored_text = restorer.restore(cleaned)
        else:
            restored_text = cleaned

        return OCRBlock(
            block_type=BlockType.PARAGRAPH,
            text=restored_text,
            bbox=bbox,
            words=words,
            page=page_num,
            confidence=avg_conf,
        )

    # ------------------------------------------------------------------ #
    # Image size handling — RapidOCR internal cap is also ~4000 px.
    # ------------------------------------------------------------------ #

    def _downscale_for_ocr(
        self, rgb_image: np.ndarray
    ) -> tuple[np.ndarray, bool]:
        """Resize ``rgb_image`` so its longest side is at most
        ``_RAPIDOCR_MAX_SIDE``. Returns the (possibly new) image and a
        flag indicating whether resizing actually happened. The original
        aspect ratio is preserved.
        """
        h, w = rgb_image.shape[:2]
        longest = max(h, w)
        if longest <= self._RAPIDOCR_MAX_SIDE:
            return rgb_image, False

        scale = self._RAPIDOCR_MAX_SIDE / float(longest)
        new_w = max(1, _round_half_away_from_zero(w * scale))
        new_h = max(1, _round_half_away_from_zero(h * scale))
        try:
            resized = _resize_image(rgb_image, new_w, new_h)
        except ImportError as exc:
            warnings.warn(
                "OCR resize backend unavailable; skipping downscale and "
                f"running RapidOCR on the original {w}x{h} image. "
                f"Original error: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return rgb_image, False
        actual_h, actual_w = resized.shape[:2]
        if (actual_h, actual_w) != (new_h, new_w):
            warnings.warn(
                "OCR resize backend returned unexpected dims "
                f"({actual_w}x{actual_h}); requested {new_w}x{new_h}.",
                RuntimeWarning,
                stacklevel=2,
            )
        return resized, True

    def _rescale_blocks(
        self,
        blocks: list[OCRBlock],
        resized_shape: tuple[int, int, int],
        original_shape: tuple[int, int, int],
    ) -> list[OCRBlock]:
        """Scale OCRBlock bounding boxes back to the original image size after
        ``_downscale_for_ocr`` has shrunk the page."""
        return _rescale_blocks(blocks, resized_shape, original_shape)

    # ------------------------------------------------------------------ #
    # Result adapter — RapidOCR ``[box, text, score]`` -> ``OCRBlock``
    # ------------------------------------------------------------------ #

    def _process_raw_results(
        self,
        raw_results: Any,
        page_num: int,
        image_height: int | None = None,
    ) -> list[OCRBlock]:
        """Convert RapidOCR ``[box, text, score]`` rows into ``OCRBlock`` objects.

        ``image_height`` is forwarded to ``_classify_block_type`` so the
        header / footer position heuristics scale with the rendered
        page rather than relying on hardcoded thresholds.
        """
        blocks: list[OCRBlock] = []

        for entry in self._iter_rapidocr_entries(raw_results):
            poly = entry["polys"]
            text = entry["text"]
            score = entry["score"]
            if score < self.config.min_confidence:
                continue
            bbox = self._coords_to_bbox(poly)
            block_type = self._classify_block_type(
                text, bbox, image_height=image_height
            )
            words = [OCRWord(text=text, bbox=bbox, confidence=score)]
            blocks.append(
                OCRBlock(
                    block_type=block_type,
                    text=text,
                    bbox=bbox,
                    words=words,
                    page=page_num,
                    confidence=score,
                    reading_order=len(blocks),
                )
            )

        blocks = self._group_into_paragraphs(blocks)
        return blocks

    def _iter_rapidocr_entries(self, raw_results: Any):
        """Yield ``{polys, text, score}`` dicts from a RapidOCR result.

        ``raw_results`` is the first element of the ``(result, elapse)``
        tuple returned by :class:`rapidocr_onnxruntime.RapidOCR`. It is
        either ``None`` (no detection) or a list of
        ``[box, text, score]`` rows where ``box`` is a 4x2 numpy array
        of corner coordinates.
        """
        if not raw_results:
            return
        for row in raw_results:
            if not row or len(row) < 3:
                continue
            box, text, score = row[0], row[1], row[2]
            yield {
                "polys": box,
                "text": text,
                "score": float(score),
            }

    @staticmethod
    def _to_rgb(image: np.ndarray) -> np.ndarray:
        """Normalise a numpy image to RGB (RapidOCR expects 3-channel)."""
        if image is None or image.size == 0:
            return image
        if len(image.shape) == 2:
            return np.stack([image] * 3, axis=-1)
        if image.shape[2] == 4:
            return image[:, :, :3]
        return image

    def _coords_to_bbox(self, coords: Any) -> BoundingBox:
        """Convert a RapidOCR polygon to ``BoundingBox``.

        ``coords`` can be either:
        - ``[[x1, y1], [x2, y2], [x3, y3], [x4, y4]]`` (RapidOCR box)
        - ``[x0, y0, x1, y1]`` (axis-aligned box)
        """
        arr = np.asarray(coords, dtype=float)
        if arr.ndim == 1 and arr.size == 4:
            x0, y0, x1, y1 = arr.tolist()
            return BoundingBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))
        if arr.ndim == 2:
            xs = arr[:, 0].tolist()
            ys = arr[:, 1].tolist()
            return BoundingBox(
                x0=float(min(xs)),
                y0=float(min(ys)),
                x1=float(max(xs)),
                y1=float(max(ys)),
            )
        return BoundingBox(x0=0.0, y0=0.0, x1=0.0, y1=0.0)

    def _classify_block_type(
        self,
        text: str,
        bbox: BoundingBox,
        *,
        image_height: int | None = None,
    ) -> BlockType:
        """Classify block type based on content and position."""
        text_stripped = (text or "").strip()
        if not text_stripped:
            return BlockType.PARAGRAPH

        heading_patterns = [
            r"^(Chương|Mục|Phần)\s+[IVXLCDM0-9]+",
            r"^Điều\s+\d+",
            r"^\d+\.\s+[A-ZĐ]",
            r"^[IVXLCDM]+\.\s+",
        ]
        for pattern in heading_patterns:
            if re.match(pattern, text_stripped, re.IGNORECASE):
                return BlockType.HEADING

        header_y_max, footer_y_min = _header_footer_thresholds(image_height)
        if bbox.y0 < header_y_max:
            return BlockType.HEADER
        if bbox.y1 > footer_y_min:
            return BlockType.FOOTER
        return BlockType.PARAGRAPH

    # ------------------------------------------------------------------ #
    # Block grouping
    # ------------------------------------------------------------------ #

    def _group_into_paragraphs(self, blocks: list[OCRBlock]) -> list[OCRBlock]:
        """Group nearby blocks into paragraphs by vertical proximity."""
        return _group_into_paragraphs(blocks, max_gap=self.config.paragraph_max_line_gap)

    def _get_vn_restorer(self) -> VNDiacriticRestorer | None:
        """Lazy-load the bundled Vietnamese wordlist restorer."""
        if self._vn_restorer is None:
            self._vn_restorer = get_default_restorer()
        return self._vn_restorer

    def _restore_diacritics_blocks(
        self, blocks: list[OCRBlock]
    ) -> list[OCRBlock]:
        """Restore Vietnamese diacritics on every block's text and words.

        Two-stage cleanup:

        1. :class:`OcrArtifactCleaner` strips well-known PP-OCRv6
           artifacts (``Ả``-as-space, scrambled heading markers
           ``ĐiuẢ``/``ChuưongẢ`` -> ``Điều``/``Chương``). Always runs
           because the cleaner is stateless and cheap.
        2. :class:`VNDiacriticRestorer` looks the cleaned tokens up in
           the corpus wordlist to recover stripped diacritics. Skipped
           if the wordlist is missing.

        No-op when ``blocks`` is empty or every block is empty.
        """
        if not blocks:
            return blocks
        cleaner = self._ocr_cleaner
        restorer = self._get_vn_restorer()

        def _restore_one(text: str) -> str:
            if not text:
                return text
            cleaned = cleaner.clean(text)
            if restorer is None:
                return cleaned
            return restorer.restore(cleaned)

        restored: list[OCRBlock] = []
        for b in blocks:
            new_text = _restore_one(b.text) if b.text else b.text
            new_words = [
                OCRWord(
                    text=_restore_one(w.text) if w.text else w.text,
                    bbox=w.bbox,
                    confidence=w.confidence,
                )
                for w in b.words
            ]
            restored.append(
                OCRBlock(
                    block_type=b.block_type,
                    text=new_text,
                    bbox=b.bbox,
                    words=new_words,
                    page=b.page,
                    confidence=b.confidence,
                    reading_order=b.reading_order,
                )
            )
        return restored

    def _calculate_average_confidence(self, blocks: list[OCRBlock]) -> float:
        return _safe_mean([b.confidence for b in blocks])

    def _check_needs_review(self, blocks: list[OCRBlock]) -> bool:
        if not blocks:
            return False
        avg = self._calculate_average_confidence(blocks)
        if avg < self.config.low_confidence_threshold:
            return True
        low_blocks = sum(
            1 for b in blocks if b.confidence < self.config.block_confidence_threshold
        )
        return low_blocks > max(1, len(blocks) // 4)

    def _generate_warnings(self, blocks: list[OCRBlock]) -> list[str]:
        if not blocks:
            return ["ocr_no_blocks_detected"]
        return []


# ---------------------------------------------------------------------- #
# Module-level helpers (kept identical to the previous engine)
# ---------------------------------------------------------------------- #

def _safe_mean(values: list[float], *, default: float = 0.0) -> float:
    if not values:
        return default
    return float(sum(values) / len(values))


def _round_half_away_from_zero(value: float) -> int:
    """Round half away from zero (1.5 -> 2, -1.5 -> -2).

    Python's built-in ``round`` uses banker's rounding (0.5 -> 0),
    which produces off-by-one rescale drift on coordinate axes that
    straddle .5. Image-coords conventions always round half up; this
    helper preserves that for the OCR round-trip.
    """
    if value >= 0:
        return int(math.floor(value + 0.5))
    return -int(math.floor(-value + 0.5))


def _scale_to_pixel(coord: float, scale: float) -> float:
    """Scale a single coordinate and round half-away-from-zero.

    Returns a float so the round-trip is identity — but the value is
    exactly representable as an integer (``int(x) == int(round(x))``).
    """
    return float(_round_half_away_from_zero(coord * scale))


def _coords_overlap_or_touch(
    a: BoundingBox, b: BoundingBox, *, tolerance: float = 1.0
) -> bool:
    """Return True if two bboxes overlap or are within ``tolerance`` pixels."""
    return not (
        a.x1 < b.x0 - tolerance
        or b.x1 < a.x0 - tolerance
        or a.y1 < b.y0 - tolerance
        or b.y1 < a.y0 - tolerance
    )


def _header_footer_thresholds(image_height: int | None) -> tuple[float, float]:
    """Return (header_y_max, footer_y_min) for header/footer classification.

    Without ``image_height`` falls back to the legacy 100/700 px
    thresholds (sensible for 200-DPI A4). With ``image_height`` uses
    proportional 7% bands so 600-DPI scans and 150-DPI scans behave
    the same.
    """
    if image_height is None:
        return 100.0, 700.0
    band = max(50.0, image_height * 0.07)
    return band, float(image_height) - band


def _resize_image(image: np.ndarray, new_w: int, new_h: int) -> np.ndarray:
    """Resize an image using cv2 (preferred) or PIL (fallback)."""
    try:
        import cv2  # type: ignore[import-not-found]

        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except ImportError:
        try:
            from PIL import Image  # type: ignore[import-not-found]

            pil_img = Image.fromarray(image)
            pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
            return np.asarray(pil_img)
        except ImportError as exc:
            raise ImportError(
                "Need OpenCV or Pillow for image resize; install one with "
                "`pip install opencv-python-headless` or `pip install Pillow`."
            ) from exc


def _rescale_blocks(
    blocks: list[OCRBlock],
    resized_shape: tuple[int, int, int],
    original_shape: tuple[int, int, int],
) -> list[OCRBlock]:
    """Scale OCRBlock bounding boxes back to the original image size."""
    rh, rw = resized_shape[:2]
    oh, ow = original_shape[:2]
    if (rh, rw) == (oh, ow):
        return blocks
    sx = ow / float(rw)
    sy = oh / float(rh)

    rescaled: list[OCRBlock] = []
    for b in blocks:
        new_bbox = BoundingBox(
            x0=_scale_to_pixel(b.bbox.x0, sx),
            y0=_scale_to_pixel(b.bbox.y0, sy),
            x1=_scale_to_pixel(b.bbox.x1, sx),
            y1=_scale_to_pixel(b.bbox.y1, sy),
        )
        new_words = [
            OCRWord(
                text=w.text,
                bbox=BoundingBox(
                    x0=_scale_to_pixel(w.bbox.x0, sx),
                    y0=_scale_to_pixel(w.bbox.y0, sy),
                    x1=_scale_to_pixel(w.bbox.x1, sx),
                    y1=_scale_to_pixel(w.bbox.y1, sy),
                ),
                confidence=w.confidence,
            )
            for w in b.words
        ]
        rescaled.append(
            OCRBlock(
                block_type=b.block_type,
                text=b.text,
                bbox=new_bbox,
                words=new_words,
                page=b.page,
                confidence=b.confidence,
                reading_order=b.reading_order,
            )
        )
    return rescaled


def _group_into_paragraphs(
    blocks: list[OCRBlock], *, max_gap: int = 10
) -> list[OCRBlock]:
    """Group nearby blocks into paragraphs by vertical proximity.

    Blocks whose top-y differs by less than ``max_gap`` pixels are
    merged into a single paragraph block. Order is preserved.
    """
    if not blocks:
        return blocks
    paragraphs: list[OCRBlock] = []
    current: list[OCRBlock] = [blocks[0]]
    for b in blocks[1:]:
        prev = current[-1]
        vertical_gap = b.bbox.y0 - prev.bbox.y1
        same_line = abs(b.bbox.y0 - prev.bbox.y0) < (prev.bbox.y1 - prev.bbox.y0) * 0.5
        if vertical_gap <= max_gap or same_line:
            current.append(b)
        else:
            paragraphs.append(_merge_blocks(current))
            current = [b]
    if current:
        paragraphs.append(_merge_blocks(current))
    return paragraphs


def _merge_blocks(blocks: list[OCRBlock]) -> OCRBlock:
    """Merge a list of same-paragraph blocks into a single block."""
    if len(blocks) == 1:
        return blocks[0]
    text = " ".join(b.text for b in blocks if b.text)
    avg_conf = _safe_mean([b.confidence for b in blocks])
    bbox = BoundingBox(
        x0=min(b.bbox.x0 for b in blocks),
        y0=min(b.bbox.y0 for b in blocks),
        x1=max(b.bbox.x1 for b in blocks),
        y1=max(b.bbox.y1 for b in blocks),
    )
    words: list[OCRWord] = []
    for b in blocks:
        words.extend(b.words)
    return OCRBlock(
        block_type=blocks[0].block_type,
        text=text,
        bbox=bbox,
        words=words,
        page=blocks[0].page,
        confidence=avg_conf,
        reading_order=blocks[0].reading_order,
    )


def bbox_to_int(bbox: BoundingBox) -> tuple[int, int, int, int]:
    return (int(bbox.x0), int(bbox.y0), int(bbox.x1), int(bbox.y1))
