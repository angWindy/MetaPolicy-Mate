"""PP-StructureV3 wrapper for layout-aware PDF processing.

PP-StructureV3 is an optional layout-aware layer that uses paddleocr
internally. It adds three capabilities on top of the plain
``OCREngine`` (RapidOCR + PP-OCRv6 Vietnamese ONNX):

* Layout detection — the page is split into regions (paragraph, title,
  table, figure, list, ...) with bounding boxes.
* Table recognition — wired and wireless tables are reconstructed into
  HTML/Markdown, with per-cell OCR.
* Markdown export — the page can be emitted as Markdown that interleaves
  paragraphs, headings, and tables in reading order.

The engine is optional. ``PDFProcessingPipeline`` only instantiates it when
``PipelineConfig.use_pp_structure=True``; otherwise it falls back to the
plain ``OCREngine`` + heuristic ``TableExtractor`` path so the dependency
footprint stays minimal for non-scan corpora.

Note: PP-StructureV3 is the only place this project still imports
``paddleocr`` directly. It is an opt-in dependency — the main text
recognition path is RapidOCR + PP-OCRv6 Vietnamese ONNX, which preserves
Vietnamese diacritics without the paddleocr dependency footprint.

CPU inference on paddlepaddle 3.3.x requires ``enable_mkldnn=False`` to
bypass the PIR/oneDNN crash documented in PaddlePaddle #77340. The flag
is forwarded as-is from :class:`PPStructureConfig`.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.ingestion.pdf_processor.schemas import (
    BoundingBox,
    OCRBlock,
    OCRResult,
    OCRWord,
    PageType,
    TableCell,
    TableStructure,
)


@dataclass
class PPStructureConfig:
    """Configuration for PP-StructureV3."""

    lang: str = "vi"
    gpu: bool = False
    enable_mkldnn: bool = False

    use_doc_orientation_classify: bool = False
    use_doc_unwarping: bool = False
    use_textline_orientation: bool = False

    use_seal_recognition: bool = False
    use_formula_recognition: bool = False
    use_chart_recognition: bool = False
    use_table_recognition: bool = True

    layout_threshold: float = 0.5
    text_rec_score_thresh: float = 0.5

    # Page-level preprocessing: how much we trust the input image and how
    # big the side limit is for the text detector. 1536 matches the default
    # used by paddleocr for A4-ish scans at 300 DPI.
    text_det_limit_side_len: int = 1536

    markdown_ignore_labels: tuple[str, ...] = field(
        default_factory=lambda: ("figure", "header", "footer", "seal")
    )


class PPStructureEngine:
    """Layout-aware OCR + table recognition via PP-StructureV3.

    Usage::

        engine = PPStructureEngine(config=PPStructureConfig())
        result = engine.process(image, page_num=1)
    """

    def __init__(self, config: PPStructureConfig | None = None):
        self.config = config or PPStructureConfig()
        self._pipeline: Any = None
        self._initialized = False

    def _lazy_init(self) -> None:
        if self._initialized:
            return

        try:
            from paddleocr._pipelines.pp_structurev3 import PPStructureV3
        except ImportError as exc:
            raise ImportError(
                "PaddleOCR is not installed; PP-StructureV3 requires paddleocr."
            ) from exc

        os.environ.setdefault("GLOG_v", "0")
        warnings.filterwarnings("ignore", category=UserWarning, module="paddle")

        kwargs: dict[str, Any] = {
            "lang": self.config.lang,
            "use_doc_orientation_classify": self.config.use_doc_orientation_classify,
            "use_doc_unwarping": self.config.use_doc_unwarping,
            "use_textline_orientation": self.config.use_textline_orientation,
            "use_seal_recognition": self.config.use_seal_recognition,
            "use_formula_recognition": self.config.use_formula_recognition,
            "use_chart_recognition": self.config.use_chart_recognition,
            "use_table_recognition": self.config.use_table_recognition,
            "enable_mkldnn": self.config.enable_mkldnn,
        }
        if self.config.gpu:
            kwargs["device"] = "gpu"

        self._pipeline = PPStructureV3(**kwargs)
        self._initialized = True

    def close(self) -> None:
        """Release PPStructureV3 reader resources and reset state.

        Mirrors :meth:`OCREngine.close` because PP-StructureV3 shares
        the same PaddlePaddle runtime and suffers the same
        GPU-pre-allocation behaviour. Long-running API processes that
        create a fresh ``PPStructureEngine`` per request will silently
        OOM after a few hundred requests unless each engine is
        explicitly closed.

        Resource-lifecycle contract — pick ONE (see
        :meth:`OCREngine.close` for the full rationale and why
        ``__del__`` is deliberately omitted):

        1. ``with PPStructureEngine(config) as engine: result = engine.process(...)``
        2. ``engine = PPStructureEngine(config); try: ... finally: engine.close()``
        3. ``engine.close()`` at the end of the request handler.
        """
        if not self._initialized:
            return
        pipeline = getattr(self, "_pipeline", None)
        if pipeline is not None:
            close = getattr(pipeline, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
        self._pipeline = None
        self._initialized = False

    def __enter__(self) -> PPStructureEngine:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def process(self, image: np.ndarray, page_num: int = 1) -> OCRResult:
        """Run PP-StructureV3 on a page image and return an OCRResult.

        ``blocks`` carries paragraph + heading regions (with reading order
        matching Paddle's layout order). ``tables`` carries the structured
        TableStructure list. ``raw_text`` is the markdown payload joined
        with newlines so the document_number extractor can pattern-match
        against it the same way it does for native text.
        """
        if not self._initialized:
            self._lazy_init()

        if image is None or image.size == 0:
            return OCRResult(
                page=page_num,
                page_type=PageType.SCAN,
                blocks=[],
                tables=[],
                raw_text="",
                average_confidence=0.0,
                needs_review=False,
                warnings=["empty image"],
            )

        if len(image.shape) == 2:
            image = np.stack([image] * 3, axis=-1)
        elif image.shape[2] == 4:
            image = image[:, :, :3]

        raw_results = list(self._pipeline.predict(image))
        if not raw_results:
            return OCRResult(
                page=page_num,
                page_type=PageType.SCAN,
                blocks=[],
                tables=[],
                raw_text="",
                average_confidence=0.0,
                needs_review=True,
                warnings=["PPStructureV3 returned no results"],
            )

        blocks: list[OCRBlock] = []
        tables: list[TableStructure] = []
        markdown_payloads: list[str] = []
        confidences: list[float] = []
        # Track whether the model reported any text regions, so we can attach
        # an actionable warning when ``blocks`` ends up empty even though the
        # model "saw" content (e.g. every score fell below the threshold). This
        # keeps ``avg_conf`` and ``needs_review`` well-defined: the empty-conf
        # path is guarded below by the ``if confidences`` ternary so we never
        # raise ``ZeroDivisionError`` here.
        seen_text_regions = False

        for page_result in raw_results:
            data = self._extract_json(page_result)
            if not data:
                continue

            res = data.get("res", data)
            page_tables, table_markdowns = self._extract_tables(res, page_num)
            tables.extend(page_tables)
            markdown_payloads.extend(table_markdowns)

            # PP-StructureV3 reports text either as layout regions or as flat
            # ``rec_texts`` (fallback path inside ``_extract_blocks``). Count
            # either as "saw text" so the warning stays accurate across model
            # versions.
            if res.get("layout_detections") or res.get("rec_texts"):
                seen_text_regions = True

            page_blocks, block_confs = self._extract_blocks(res, page_num)
            blocks.extend(page_blocks)
            confidences.extend(block_confs)

            md_obj = getattr(page_result, "markdown", None)
            if isinstance(md_obj, dict):
                md_text = md_obj.get("markdown_texts")
                if isinstance(md_text, str) and md_text.strip():
                    markdown_payloads.append(md_text)

        raw_text = "\n\n".join(piece for piece in markdown_payloads if piece)
        # Guarded via ``_safe_mean`` — an empty ``confidences`` list
        # (typical when every score falls below the threshold) returns the
        # default ``0.0`` instead of raising ``ZeroDivisionError``. The
        # fallback keeps ``needs_review`` truthful (always < threshold
        # ⇒ review).
        from src.ingestion.pdf_processor.ocr_engine import _safe_mean

        avg_conf = _safe_mean(confidences)
        needs_review = avg_conf < self.config.text_rec_score_thresh

        warnings: list[str] = []
        if not blocks and seen_text_regions:
            warnings.append(
                "PPStructureV3 detected text regions but every score fell "
                "below the recognition threshold; nothing was extracted."
            )
        elif not blocks and not raw_text:
            warnings.append("PPStructureV3 detected no text on this page.")

        return OCRResult(
            page=page_num,
            page_type=PageType.SCAN,
            blocks=blocks,
            tables=tables,
            raw_text=raw_text,
            average_confidence=avg_conf,
            needs_review=needs_review,
            warnings=warnings,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_json(page_result: Any) -> dict[str, Any] | None:
        if page_result is None:
            return None
        raw = getattr(page_result, "json", None)
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", errors="ignore")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return None
        return None

    def _extract_blocks(
        self,
        res: dict[str, Any],
        page_num: int,
    ) -> tuple[list[OCRBlock], list[float]]:
        """Convert layout-detected text regions into OCRBlock objects."""
        blocks: list[OCRBlock] = []
        confs: list[float] = []

        # PP-StructureV3 puts layout-region info in ``layout_detections``
        # when ``format_block_content=True`` is set on predict(); otherwise
        # text lives in ``dt_polys``/``rec_texts``/``rec_scores`` (same
        # shape paddleocr returns). We handle both shapes so the engine
        # remains robust across model versions.
        layout = res.get("layout_detections") or []

        for idx, region in enumerate(layout):
            label = region.get("label", "paragraph").lower()
            bbox = region.get("bbox") or region.get("box")
            block_type = self._layout_label_to_block_type(label)
            cells = region.get("block_content") or region.get("content")
            region_text, region_confs = self._flatten_block_content(cells)

            if not region_text and bbox is not None:
                continue

            # Compute the per-region confidence once and reuse it for both the
            # OCRBlock and its OCRWord. The single guard keeps ``len()`` from
            # ever being zero (an empty ``region_confs`` would otherwise
            # raise ``ZeroDivisionError`` if the ternary guard were ever
            # dropped in one of the two call sites).
            if region_confs:
                region_confidence = sum(region_confs) / len(region_confs)
            else:
                region_confidence = 0.0

            block_bbox = self._bbox_or_none(bbox)
            blocks.append(
                OCRBlock(
                    block_type=block_type,
                    text=region_text,
                    bbox=block_bbox,
                    words=[
                        OCRWord(
                            text=region_text,
                            bbox=block_bbox or BoundingBox(),
                            confidence=region_confidence,
                        )
                    ],
                    page=page_num,
                    confidence=region_confidence,
                    reading_order=idx,
                )
            )
            confs.extend(region_confs)

        # Fallback: when layout_detections is empty, treat each
        # dt_polys/rec_texts region as a paragraph.
        if not blocks and res.get("rec_texts"):
            polys = res.get("dt_polys") or []
            texts = res.get("rec_texts") or []
            scores = res.get("rec_scores") or []
            polys = np.asarray(polys).tolist() if hasattr(polys, "tolist") else polys
            for idx, (poly, text, score) in enumerate(zip(polys, texts, scores)):
                score = float(score)
                if score < self.config.text_rec_score_thresh:
                    continue
                bbox = self._bbox_or_none(poly)
                blocks.append(
                    OCRBlock(
                        block_type=BlockType.PARAGRAPH,
                        text=text,
                        bbox=bbox,
                        words=[OCRWord(text=text, bbox=bbox or BoundingBox(), confidence=score)],
                        page=page_num,
                        confidence=score,
                        reading_order=idx,
                    )
                )
                confs.append(score)

        return blocks, confs

    @staticmethod
    def _flatten_block_content(cells: Any) -> tuple[str, list[float]]:
        """Walk the nested ``block_content`` produced by PP-StructureV3.

        Invariant: every score in the returned ``scores`` list is a
        ``float`` in the open interval ``(0.0, 1.0]``. Zero / falsy
        scores are filtered out so the caller's ``if region_confs:`` guard
        becomes a typed precondition (``0 < len(confs)``) rather than a
        fragile truthiness fallback; a future refactor that drops the
        ``if region_confs:`` check at the call site can no longer trigger
        a ``ZeroDivisionError`` on a list of ``[0.0]``-style entries.
        """
        if cells is None:
            return "", []
        if isinstance(cells, str):
            return cells, []
        if isinstance(cells, list):
            pieces: list[str] = []
            scores: list[float] = []
            for item in cells:
                sub_text, sub_scores = PPStructureEngine._flatten_block_content(item)
                if sub_text:
                    pieces.append(sub_text)
                scores.extend(sub_scores)
            return "\n".join(pieces), scores
        if isinstance(cells, dict):
            text = cells.get("text") or cells.get("content") or ""
            raw_score = cells.get("score") or cells.get("confidence")
            try:
                score = float(raw_score) if raw_score is not None else 0.0
            except (TypeError, ValueError):
                score = 0.0
            # Filter zeros / out-of-range scores so the invariant holds.
            # ``0.0`` here comes from either an explicit 0 or a missing
            # field (handled above) — both mean "no score given", not "zero
            # confidence".
            if score <= 0.0 or score > 1.0:
                return (text if isinstance(text, str) else ""), []
            return (text if isinstance(text, str) else ""), [score]
        return "", []

    @staticmethod
    def _layout_label_to_block_type(label: str):
        from src.ingestion.pdf_processor.schemas import BlockType

        label = (label or "").lower()
        if label in {"title", "heading", "subheading"}:
            return BlockType.HEADING
        if label == "table":
            return BlockType.TABLE
        if label in {"list", "list_item"}:
            return BlockType.LIST
        if label in {"figure", "image"}:
            return BlockType.FIGURE
        if label in {"header", "page_header"}:
            return BlockType.HEADER
        if label in {"footer", "page_footer"}:
            return BlockType.FOOTER
        if label in {"seal", "stamp"}:
            return BlockType.STAMP
        return BlockType.PARAGRAPH

    @staticmethod
    def _bbox_or_none(coords: Any) -> BoundingBox | None:
        if coords is None:
            return None
        arr = np.asarray(coords, dtype=float)
        if arr.size == 0:
            return None
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
        return None

    def _extract_tables(
        self,
        res: dict[str, Any],
        page_num: int,
    ) -> tuple[list[TableStructure], list[str]]:
        """Reconstruct tables from ``res['table_blocks']`` (or fallback keys)."""
        tables: list[TableStructure] = []
        markdowns: list[str] = []

        table_blocks = res.get("table_blocks") or res.get("tables") or []
        for t_idx, table in enumerate(table_blocks):
            bbox = self._bbox_or_none(table.get("bbox"))
            html = table.get("html")
            markdown_text = table.get("markdown") or table.get("pred")
            cells = table.get("cells") or []

            cells_models: list[TableCell] = []
            max_row = 0
            max_col = 0
            for cell in cells:
                row = int(cell.get("row", 0))
                col = int(cell.get("col", 0))
                max_row = max(max_row, row)
                max_col = max(max_col, col)
                cells_models.append(
                    TableCell(
                        row=row,
                        col=col,
                        text=str(cell.get("text", "") or ""),
                        bbox=self._bbox_or_none(cell.get("bbox")),
                        is_header=bool(cell.get("is_header", False)),
                        row_span=int(cell.get("row_span", 1) or 1),
                        col_span=int(cell.get("col_span", 1) or 1),
                    )
                )

            if not cells_models and html:
                # Some model versions expose the table as HTML only.
                # Synthesise a single-cell table so downstream code can still
                # surface the HTML payload.
                cells_models = [
                    TableCell(
                        row=0,
                        col=0,
                        text=html,
                        bbox=bbox,
                        is_header=False,
                    )
                ]
                max_row = max_col = 1

            structure = TableStructure(
                rows=max_row + 1,
                cols=max_col + 1,
                cells=cells_models,
                bbox=bbox,
                page=page_num,
                html=html,
                markdown=markdown_text,
            )
            # Refresh derived representations so the rest of the pipeline
            # gets consistent HTML/markdown regardless of which the model
            # provided.
            structure.html = html or structure.to_html()
            structure.markdown = markdown_text or structure.to_markdown()
            tables.append(structure)
            if structure.markdown:
                markdowns.append(structure.markdown)

        return tables, markdowns

    def warmup(self) -> None:
        """Lazy initialise the model so the first real call is faster."""
        self._lazy_init()
