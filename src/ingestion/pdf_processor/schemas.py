"""Schemas for PDF processing pipeline.

Unified document model aligned with docs/pdf_processing_pipeline.md Section 13.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PageType(StrEnum):
    """Page classification types per pipeline docs."""

    DIGITAL = "digital"  # Native text layer
    SCAN = "scan"  # Image only
    HYBRID = "hybrid"  # Mixed text and images


class BlockType(StrEnum):
    """Types of content blocks extracted from pages."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    TABLE = "table"
    LIST = "list"
    FIGURE = "figure"
    SIGNATURE = "signature"
    STAMP = "stamp"
    FOOTER = "footer"
    HEADER = "header"


class OCRConfidence(StrEnum):
    """Confidence levels for OCR results."""

    HIGH = "high"  # > 0.9
    MEDIUM = "medium"  # 0.7 - 0.9
    LOW = "low"  # 0.5 - 0.7
    VERY_LOW = "very_low"  # < 0.5


class BoundingBox(BaseModel):
    """Bounding box for content positioning."""

    x0: float = Field(description="Left coordinate")
    y0: float = Field(description="Top coordinate")
    x1: float = Field(description="Right coordinate")
    y1: float = Field(description="Bottom coordinate")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


class TableCell(BaseModel):
    """Individual cell in a table structure."""

    row: int = Field(description="Row index (0-based)")
    col: int = Field(description="Column index (0-based)")
    text: str = Field(description="Cell text content")
    bbox: BoundingBox | None = Field(default=None, description="Cell bounding box")
    is_header: bool = Field(default=False, description="Whether this is a header cell")
    row_span: int = Field(default=1, description="Number of rows spanned")
    col_span: int = Field(default=1, description="Number of columns spanned")


class TableStructure(BaseModel):
    """Structured table representation with multiple formats."""

    rows: int = Field(description="Total number of rows")
    cols: int = Field(description="Total number of columns")
    cells: list[TableCell] = Field(description="All cells in the table")
    bbox: BoundingBox | None = Field(default=None, description="Table bounding box")
    page: int = Field(description="Page number")
    html: str | None = Field(default=None, description="HTML representation")
    markdown: str | None = Field(default=None, description="Markdown representation")
    image_crop: bytes | None = Field(default=None, description="Original image crop")

    def to_html(self) -> str:
        """Convert cells to HTML table format."""
        if not self.cells:
            return ""

        # Build grid
        grid: dict[int, dict[int, TableCell]] = {}
        for cell in self.cells:
            if cell.row not in grid:
                grid[cell.row] = {}
            grid[cell.row][cell.col] = cell

        rows_html = []
        for row_idx in range(self.rows):
            cells_html = []
            row_cells = grid.get(row_idx, {})
            for col_idx in range(self.cols):
                cell = row_cells.get(col_idx)
                if cell:
                    tag = "th" if cell.is_header else "td"
                    attrs = ""
                    if cell.row_span > 1:
                        attrs += f' rowspan="{cell.row_span}"'
                    if cell.col_span > 1:
                        attrs += f' colspan="{cell.col_span}"'
                    cells_html.append(f"<{tag}{attrs}>{cell.text}</{tag}>")
                else:
                    cells_html.append("<td></td>")
            rows_html.append(f"<tr>{''.join(cells_html)}</tr>")

        return f"<table>{''.join(rows_html)}</table>"

    def to_markdown(self) -> str:
        """Convert cells to Markdown table format."""
        if not self.cells:
            return ""

        # Build grid
        grid: dict[int, dict[int, TableCell]] = {}
        for cell in self.cells:
            if cell.row not in grid:
                grid[cell.row] = {}
            grid[cell.row][cell.col] = cell

        lines = []
        for row_idx in range(self.rows):
            row_cells = grid.get(row_idx, {})
            values = []
            for col_idx in range(self.cols):
                cell = row_cells.get(col_idx)
                values.append(cell.text if cell else "")
            lines.append("| " + " | ".join(values) + " |")
            if row_idx == 0:
                lines.append("| " + " | ".join(["---"] * self.cols) + " |")

        return "\n".join(lines)


class OCRWord(BaseModel):
    """Individual word recognized by OCR."""

    text: str
    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)


class OCRBlock(BaseModel):
    """OCR result for a text block/region."""

    block_type: BlockType = Field(default=BlockType.PARAGRAPH)
    text: str = Field(description="Recognized text content")
    bbox: BoundingBox | None = Field(default=None, description="Block bounding box")
    words: list[OCRWord] = Field(default_factory=list, description="Individual words")
    confidence: float = Field(ge=0.0, le=1.0, description="Average confidence score")
    page: int = Field(description="Page number")
    reading_order: int = Field(default=0, description="Order on page")

    @property
    def confidence_level(self) -> OCRConfidence:
        """Categorize confidence level."""
        if self.confidence >= 0.9:
            return OCRConfidence.HIGH
        elif self.confidence >= 0.7:
            return OCRConfidence.MEDIUM
        elif self.confidence >= 0.5:
            return OCRConfidence.LOW
        return OCRConfidence.VERY_LOW


class OCRResult(BaseModel):
    """Complete OCR result for a page."""

    page: int = Field(description="Page number")
    page_type: PageType = Field(description="Classified page type")
    blocks: list[OCRBlock] = Field(default_factory=list, description="Text blocks")
    tables: list[TableStructure] = Field(default_factory=list, description="Extracted tables")
    raw_text: str = Field(description="Concatenated raw text")
    average_confidence: float = Field(ge=0.0, le=1.0)
    needs_review: bool = Field(default=False, description="Needs VLM review")
    warnings: list[str] = Field(default_factory=list, description="Processing warnings")


class ProcessedPage(BaseModel):
    """Processed page with both native and OCR content."""

    page_number: int = Field(description="1-based page number")
    page_type: PageType = Field(description="Page classification")
    native_text: str = Field(default="", description="Extracted native text")
    ocr_result: OCRResult | None = Field(default=None, description="OCR result if applicable")
    is_reviewed: bool = Field(default=False, description="Has been reviewed")


class LegalStructure(BaseModel):
    """Legal document structure hierarchy."""

    chapter: str | None = Field(default=None, description="Chapter (Chương)")
    chapter_number: str | None = Field(default=None, description="Chapter number")
    article: str | None = Field(default=None, description="Article (Điều)")
    article_number: str | None = Field(default=None, description="Article number")
    clause: str | None = Field(default=None, description="Clause (Khoản)")
    clause_number: str | None = Field(default=None, description="Clause number")
    point: str | None = Field(default=None, description="Point (Điểm)")
    point_number: str | None = Field(default=None, description="Point number")
    heading: str | None = Field(default=None, description="Full heading text")
    heading_path: list[str] = Field(default_factory=list, description="Full path in hierarchy")


class NormalizedBlock(BaseModel):
    """Normalized content block aligned with Unified Document Model.

    Matches docs/pdf_processing_pipeline.md Section 13 schema.
    """

    block_type: BlockType
    page: int
    bbox: BoundingBox | None = None

    # Legal structure
    section: LegalStructure | None = None

    # Content
    raw_text: str = Field(description="Original raw text or OCR output")
    normalized_text: str = Field(description="Normalized/cleaned text")

    # Provenance
    source: str = Field(
        default="pdf_text",
        description="Source type: pdf_text, ocr, table_parser, vlm_review"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    vlm_corrected: bool = Field(default=False)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    # Marked True when the parent page's OCR ``average_confidence`` fell
    # below the low-confidence threshold (default 0.6). The downstream
    # ``extract_sections`` skips regex-based heading detection on these
    # blocks and routes them to a semantic chunking fallback so heading
    # detection doesn't shred a low-quality scan.
    low_confidence: bool = False

    # Table specific
    table: TableStructure | None = None

    def to_unified_dict(self) -> dict[str, Any]:
        """Convert to unified document model format."""
        result: dict[str, Any] = {
            "page": self.page,
            "type": self.block_type.value,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "provenance": {
                "source": self.source,
                "confidence": self.confidence,
            },
        }
        if self.bbox:
            result["provenance"]["bbox"] = self.bbox.to_list()
        if self.section:
            result["section"] = {
                "chapter": self.section.chapter,
                "article": self.section.article,
                "clause": self.section.clause,
                "point": self.section.point,
            }
        if self.table:
            result["content"] = {
                "type": "table",
                "html": self.table.html,
                "markdown": self.table.markdown,
            }
        return result


class ProcessedDocument(BaseModel):
    """Complete processed document with all pages."""

    document_id: str = Field(description="Document identifier")
    filename: str = Field(description="Original filename")
    sha256: str = Field(description="File checksum")
    pages: list[ProcessedPage] = Field(default_factory=list)
    blocks: list[NormalizedBlock] = Field(default_factory=list)
    total_pages: int = Field(description="Total page count")
    scan_pages: int = Field(default=0, description="Number of scan pages")
    digital_pages: int = Field(default=0, description="Number of digital pages")
    hybrid_pages: int = Field(default=0, description="Number of hybrid pages")
    processing_timestamp: datetime = Field(default_factory=datetime.now)

    # Metadata
    source_url: str | None = None
    document_number: str | None = None
    issued_date: datetime | None = None
    issued_by: str | None = None

    # Aggregated stats — set by ``PDFProcessingPipeline.get_stats``.
    # Used by bench scripts and the ingestion driver to surface pages
    # below the low-confidence threshold so operators can flag them
    # for human review.
    low_confidence_page_count: int = Field(
        default=0,
        description="Number of OCR pages with average_confidence < low_confidence_threshold.",
    )
    low_confidence_page_numbers: list[int] = Field(
        default_factory=list,
        description="Page numbers flagged for low-confidence review.",
    )
    needs_review: bool = Field(
        default=False,
        description="True when at least one page is below the low-confidence threshold.",
    )

    @property
    def has_scan_content(self) -> bool:
        """Check if document contains scan pages."""
        return self.scan_pages > 0 or self.hybrid_pages > 0

    def get_page(self, page_number: int) -> ProcessedPage | None:
        """Get page by number (1-based)."""
        for page in self.pages:
            if page.page_number == page_number:
                return page
        return None


class VLMReviewRequest(BaseModel):
    """Request for VLM-assisted review of OCR results."""

    page: int
    original_image_crop: bytes
    raw_ocr: str
    ocr_confidence: float
    context: str | None = None
    prompt: str = Field(
        default="Hãy sửa lỗi OCR nếu thấy. Chỉ sửa khi thấy bằng chứng rõ ràng trên ảnh. Không diễn giải hay bổ sung nội dung."
    )


class VLMReviewResult(BaseModel):
    """Result from VLM-assisted review."""

    raw_ocr: str = Field(description="Original OCR text")
    corrected: str = Field(description="Corrected text")
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    review_method: str = Field(default="vlm")
    confidence: float = Field(ge=0.0, le=1.0)
    reviewed_at: datetime = Field(default_factory=datetime.now)
