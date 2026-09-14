"""Table extraction for PDF documents.

Per docs/pdf_processing_pipeline.md Section 7:
- Preserve table structure (not flatten to plain text)
- Store multiple representations: image crop, JSON, HTML, Markdown
- Handle merged cells, rowspan, colspan

Two backends are available:

* **Heuristic** (default): opencv-based line detection + uniform grid
  fallback. Used when ``use_pp_structure=False`` on :class:`TableExtractor`
  (or :class:`PipelineConfig`). No heavy model dependency; works on any
  PDF where the table border is visible.
* **PP-StructureV3**: when ``use_pp_structure=True``, the heuristic is
  bypassed and the table structures returned by :class:`PPStructureEngine`
  are forwarded verbatim. PP-StructureV3 is an optional layout-aware layer;
  the main OCR text recognition path in this project uses RapidOCR +
  PP-OCRv6 Vietnamese ONNX.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.ingestion.pdf_processor.ocr_engine import bbox_to_int
from src.ingestion.pdf_processor.schemas import (
    BoundingBox,
    TableCell,
    TableStructure,
)


@dataclass
class TableConfig:
    """Configuration for table extraction."""

    # Detection
    min_table_width: int = 50
    min_table_height: int = 30
    min_row_height: int = 10
    min_col_width: int = 20

    line_threshold: float = 0.5
    table_border_gap: int = 5

    min_col_separator_width: int = 2
    merge_tolerance: int = 5

    ocr_confidence_threshold: float = 0.5

    # Backend selector. False = heuristic (default), True = delegate to a
    # :class:`PPStructureEngine` instance attached by the pipeline.
    use_pp_structure: bool = False


class TableExtractor:
    """Extracts tables from PDF page images.

    When ``config.use_pp_structure=True`` and a PPStructureEngine is attached
    via :meth:`set_pp_structure`, the heuristic backend is bypassed and the
    layout-aware engine is asked to produce table structures for the page.

    Usage::

        extractor = TableExtractor(config=TableConfig())
        tables = extractor.extract_tables(page_image, page_num=1)
    """

    def __init__(self, config: TableConfig | None = None):
        self.config = config or TableConfig()
        self._cv2_available = False
        self._pp_engine = None
        try:
            import cv2
            self.cv2 = cv2
            self._cv2_available = True
        except ImportError:
            pass

    def set_pp_structure(self, pp_engine: object | None) -> None:
        """Attach a :class:`PPStructureEngine` to delegate to.

        The extractor stores the engine by reference; callers control when
        the heavy model is instantiated via :class:`PipelineConfig`.
        """
        self._pp_engine = pp_engine

    def extract_tables(self, image: np.ndarray, page_num: int = 1) -> list[TableStructure]:
        """Detect and extract tables from a page image.

        Args:
            image: Page image as numpy array (H, W, C) in RGB/BGR or grayscale
            page_num: Page number for metadata

        Returns:
            List of extracted TableStructure objects
        """
        if self.config.use_pp_structure and self._pp_engine is not None:
            return self._extract_via_pp_structure(image, page_num)

        if not self._cv2_available:
            return []

        gray = (
            self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)
            if len(image.shape) == 3
            else image
        )
        if gray.size == 0:
            return []

        tables: list[TableStructure] = []
        for region_bbox in self._detect_table_regions(gray):
            table = self._extract_table_structure(gray, region_bbox, page_num)
            if table:
                tables.append(table)

        return tables

    def _extract_via_pp_structure(
        self,
        image: np.ndarray,
        page_num: int,
    ) -> list[TableStructure]:
        """Delegate table extraction to PPStructureEngine.

        ``process()`` is more expensive than the heuristic (it lays out the
        whole page), so the caller is expected to memoize the result by
        page number. We deliberately call it from the table extractor only
        because the pipeline wires PP-Structure once per page elsewhere.
        """
        result = self._pp_engine.process(image, page_num=page_num)
        return list(result.tables)

    def _detect_table_regions(self, gray: np.ndarray) -> list[BoundingBox]:
        """Detect potential table regions via line detection."""
        edges = self.cv2.Canny(gray, 50, 150)

        horizontal_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (50, 1))
        horizontal_lines = self.cv2.morphologyEx(edges, self.cv2.MORPH_OPEN, horizontal_kernel)

        vertical_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (1, 50))
        vertical_lines = self.cv2.morphologyEx(edges, self.cv2.MORPH_OPEN, vertical_kernel)

        combined = self.cv2.add(horizontal_lines, vertical_lines)

        contours, _ = self.cv2.findContours(
            combined, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE
        )

        regions: list[BoundingBox] = []
        for contour in contours:
            x, y, w, h = self.cv2.boundingRect(contour)
            if w >= self.config.min_table_width and h >= self.config.min_table_height:
                region = gray[y : y + h, x : x + w]
                if self._looks_like_table(region):
                    regions.append(
                        BoundingBox(x0=float(x), y0=float(y), x1=float(x + w), y1=float(y + h))
                    )
        return regions

    def _looks_like_table(self, region: np.ndarray) -> bool:
        """Check if a region has grid-like structure."""
        if region.size == 0:
            return False
        edges = self.cv2.Canny(region, 50, 150)

        horizontal_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (30, 1))
        h_lines = self.cv2.morphologyEx(edges, self.cv2.MORPH_OPEN, horizontal_kernel)

        vertical_kernel = self.cv2.getStructuringElement(self.cv2.MORPH_RECT, (1, 30))
        v_lines = self.cv2.morphologyEx(edges, self.cv2.MORPH_OPEN, vertical_kernel)

        h_density = np.sum(h_lines > 0) / h_lines.size
        v_density = np.sum(v_lines > 0) / v_lines.size

        return h_density > 0.01 and v_density > 0.01

    def _extract_table_structure(
        self, gray: np.ndarray, table_bbox: BoundingBox, page_num: int
    ) -> TableStructure | None:
        """Extract structure from a detected table region."""
        x0, y0, x1, y1 = bbox_to_int(table_bbox)
        table_img = gray[y0:y1, x0:x1]
        if table_img.size == 0:
            return None

        h_lines, v_lines = self._detect_grid_lines(table_img)

        if not h_lines or not v_lines:
            return self._extract_simple_grid(table_img, table_bbox, page_num)

        row_boundaries = [0] + sorted(h_lines) + [table_img.shape[0]]
        col_boundaries = [0] + sorted(v_lines) + [table_img.shape[1]]

        cells: list[TableCell] = []
        for row_idx in range(len(row_boundaries) - 1):
            for col_idx in range(len(col_boundaries) - 1):
                cell = TableCell(
                    row=row_idx,
                    col=col_idx,
                    text="",
                    bbox=BoundingBox(
                        x0=float(x0 + col_boundaries[col_idx]),
                        y0=float(y0 + row_boundaries[row_idx]),
                        x1=float(x0 + col_boundaries[col_idx + 1]),
                        y1=float(y0 + row_boundaries[row_idx + 1]),
                    ),
                    is_header=(row_idx == 0),
                )
                cells.append(cell)

        table = TableStructure(
            rows=len(row_boundaries) - 1,
            cols=len(col_boundaries) - 1,
            cells=cells,
            bbox=table_bbox,
            page=page_num,
        )
        table.html = table.to_html()
        table.markdown = table.to_markdown()
        table.image_crop = table_img.tobytes()
        return table

    def _detect_grid_lines(self, table_img: np.ndarray) -> tuple[list[int], list[int]]:
        """Detect horizontal/vertical grid lines via projection."""
        h_lines: list[int] = []
        v_lines: list[int] = []

        threshold_h = table_img.shape[1] * 0.1
        in_line = False
        line_start = 0
        for y, val in enumerate(np.sum(table_img < 128, axis=1)):
            if val > threshold_h and not in_line:
                in_line = True
                line_start = y
            elif val <= threshold_h and in_line:
                in_line = False
                if y - line_start >= self.config.min_row_height:
                    h_lines.append((line_start + y) // 2)

        threshold_v = table_img.shape[0] * 0.1
        in_line = False
        line_start = 0
        for x, val in enumerate(np.sum(table_img < 128, axis=0)):
            if val > threshold_v and not in_line:
                in_line = True
                line_start = x
            elif val <= threshold_v and in_line:
                in_line = False
                if x - line_start >= self.config.min_col_width:
                    v_lines.append((line_start + x) // 2)

        return h_lines, v_lines

    def _extract_simple_grid(
        self, table_img: np.ndarray, table_bbox: BoundingBox, page_num: int
    ) -> TableStructure:
        """Fallback: extract using uniform grid when no lines detected."""
        rows = max(2, int(table_img.shape[0] / 30))
        cols = max(2, int(table_img.shape[1] / 60))

        cells: list[TableCell] = []
        row_height = table_img.shape[0] / rows
        col_width = table_img.shape[1] / cols

        for row_idx in range(rows):
            for col_idx in range(cols):
                cell = TableCell(
                    row=row_idx,
                    col=col_idx,
                    text="",
                    bbox=BoundingBox(
                        x0=float(int(table_bbox.x0) + col_idx * col_width),
                        y0=float(int(table_bbox.y0) + row_idx * row_height),
                        x1=float(int(table_bbox.x0) + (col_idx + 1) * col_width),
                        y1=float(int(table_bbox.y0) + (row_idx + 1) * row_height),
                    ),
                    is_header=(row_idx == 0),
                )
                cells.append(cell)

        table = TableStructure(
            rows=rows, cols=cols, cells=cells,
            bbox=table_bbox, page=page_num,
        )
        table.html = table.to_html()
        table.markdown = table.to_markdown()
        return table
