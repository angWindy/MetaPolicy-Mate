"""Document Normalizer for PDF processing pipeline.

Provides:
- Unified document model (NormalizedBlock)
- OCR error detection (suspicious characters)
- Rule-based validation (article numbers, dates, etc)
- Provenance preservation
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.ingestion.pdf_processor.schemas import (
    BlockType,
    LegalStructure,
    NormalizedBlock,
    OCRResult,
    ProcessedPage,
)


@dataclass
class NormalizerConfig:
    """Configuration for document normalization."""

    # Text normalization
    normalize_whitespace: bool = True
    normalize_vietnamese_quotes: bool = True
    remove_extra_spaces: bool = True

    # Number normalization
    normalize_numbers: bool = True
    normalize_dates: bool = True

    # Legal structure detection
    detect_chapters: bool = True
    detect_articles: bool = True
    detect_clauses: bool = True
    detect_points: bool = True

    # Validation
    validate_article_numbers: bool = True
    validate_dates: bool = True
    flag_suspicious_ocr: bool = True


# Vietnamese-style quotes
VN_OPEN_QUOTE = "\u201C"  # "
VN_CLOSE_QUOTE = "\u201D"  # "
VN_OPEN_QUOTE_ALT = "\u00AB"  # <<
VN_CLOSE_QUOTE_ALT = "\u00BB"  # >>

# Suspicious OCR patterns - chars that look similar to digits
SUSPICIOUS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Điều\s+[l1|i]\d*", re.IGNORECASE), "suspect_article"),
    (re.compile(r"Khoản\s+[l|i|1]\s", re.IGNORECASE), "suspect_clause"),
    (re.compile(r"\d+[O|o]\d+"), "suspect_number_o"),
    (re.compile(r"\d+[S|s]\d+"), "suspect_number_s"),
    (re.compile(r"20[1-9][0-9][S|s]"), "suspect_year"),
    (re.compile(r"\d+\s*ngay\b", re.IGNORECASE), "suspect_ngay"),
]

# Date patterns
DATE_PATTERN = re.compile(r"\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}")

# Legal structure patterns
CHAPTER_PATTERN = re.compile(
    r"^\s*(Chương|Mục|Phần)\s+([IVXLCDM0-9]+)\b(.*)$", re.IGNORECASE
)
ARTICLE_PATTERN = re.compile(
    r"^\s*Điều\s+([0-9]+[a-zA-Z]?)\s*[.:\-]?\s*(.*)$", re.IGNORECASE
)
CLAUSE_PATTERN = re.compile(r"^\s*([0-9]+)\s*[.)]\s+(.+)$")
POINT_PATTERN = re.compile(r"^\s*([a-zđ])\s*[.)]\s+(.+)$", re.IGNORECASE)


def normalize_text(text: str, config: NormalizerConfig | None = None) -> str:
    """Normalize text content for indexing."""
    if not text:
        return ""
    config = config or NormalizerConfig()
    normalized = text

    if config.normalize_whitespace:
        normalized = re.sub(r"\s+", " ", normalized).strip()

    if config.normalize_vietnamese_quotes:
        normalized = (
            normalized.replace('"', VN_CLOSE_QUOTE)
            .replace('"', VN_OPEN_QUOTE)
            .replace("<<", VN_OPEN_QUOTE_ALT)
            .replace(">>", VN_CLOSE_QUOTE_ALT)
        )

    if config.normalize_numbers:
        normalized = re.sub(r"(\d+)[.,](\d{3})", r"\1\2", normalized)

    return normalized


def check_suspicious_content(text: str) -> list[str]:
    """Detect OCR mis-reads in text.

    Vietnamese legal docs often have chars that OCR confuses:
    - l / I / 1 with digit 1
    - O / 0 with digit 0
    - S / 5 confusion

    Returns:
        List of warning type names
    """
    return [
        warning_type
        for pattern, warning_type in SUSPICIOUS_PATTERNS
        if pattern.search(text)
    ]


def update_legal_structure(
    text: str,
    current: LegalStructure,
    config: NormalizerConfig | None = None,
) -> LegalStructure:
    """Update legal structure context based on text content."""
    config = config or NormalizerConfig()
    updated = current.model_copy()

    if config.detect_chapters:
        match = CHAPTER_PATTERN.match(text)
        if match:
            updated.chapter = f"{match.group(1)} {match.group(2)}"
            updated.chapter_number = match.group(2)
            updated.heading = updated.chapter
            updated.article = updated.article_number = None
            updated.clause = updated.clause_number = None
            updated.point = updated.point_number = None
            return updated

    if config.detect_articles:
        match = ARTICLE_PATTERN.match(text)
        if match:
            article_num = match.group(1)
            title = match.group(2).strip()
            updated.article = f"Điều {article_num}" + (f". {title}" if title else "")
            updated.article_number = article_num
            updated.heading = updated.article
            updated.clause = updated.clause_number = None
            updated.point = updated.point_number = None
            return updated

    if config.detect_clauses and updated.article:
        match = CLAUSE_PATTERN.match(text)
        if match:
            updated.clause = f"Khoản {match.group(1)}"
            updated.clause_number = match.group(1)
            updated.point = updated.point_number = None
            return updated

    if config.detect_points and updated.article:
        match = POINT_PATTERN.match(text)
        if match:
            point_num = match.group(1).lower()
            updated.point = f"Điểm {point_num}"
            updated.point_number = point_num
            return updated

    return updated


class DocumentNormalizer:
    """Normalizer for converting OCR/parsed content to unified format.

    Per docs/pdf_processing_pipeline.md Section 13:
    - Unified Document Model
    - Paragraph and Table schemas
    - Provenance preservation
    - Rule-based validation

    Usage:
        normalizer = DocumentNormalizer()
        blocks = normalizer.normalize_ocr_result(ocr_result, page_num=1)
    """

    def __init__(self, config: NormalizerConfig | None = None):
        self.config = config or NormalizerConfig()

    def normalize_ocr_result(
        self,
        ocr_result: OCRResult,
        page_num: int | None = None,
        low_confidence_threshold: float = 0.6,
    ) -> list[NormalizedBlock]:
        """Normalize OCR result to unified blocks.

        ``low_confidence_threshold`` controls the per-page audit flag —
        when ``ocr_result.average_confidence`` falls below this value,
        every block on the page is marked ``low_confidence=True`` in
        the resulting :class:`NormalizedBlock`. Downstream extraction
        (``extract_sections`` and the chunker) honours the flag.
        """
        blocks: list[NormalizedBlock] = []
        page = page_num if page_num is not None else ocr_result.page
        current_structure = LegalStructure()

        page_low_conf = (
            ocr_result.average_confidence < low_confidence_threshold
        )

        for ocr_block in ocr_result.blocks:
            normalized_text = normalize_text(ocr_block.text)
            current_structure = update_legal_structure(normalized_text, current_structure, self.config)

            block = NormalizedBlock(
                block_type=ocr_block.block_type,
                page=page,
                bbox=ocr_block.bbox,
                section=current_structure if current_structure.article else None,
                raw_text=ocr_block.text,
                normalized_text=normalized_text,
                source="ocr",
                confidence=ocr_block.confidence,
                vlm_corrected=False,
                low_confidence=page_low_conf,
            )

            if self.config.flag_suspicious_ocr:
                warnings = check_suspicious_content(normalized_text)
                if warnings:
                    block.corrections = [{"type": w} for w in warnings]

            blocks.append(block)

        # Process tables
        for table in ocr_result.tables:
            block = NormalizedBlock(
                block_type=BlockType.TABLE,
                page=page,
                bbox=table.bbox,
                section=current_structure if current_structure.article else None,
                raw_text=table.markdown or "",
                normalized_text=table.markdown or "",
                source="table_parser",
                confidence=0.9,
                table=table,
                low_confidence=page_low_conf,
            )
            blocks.append(block)

        return blocks

    def normalize_processed_page(
        self, page: ProcessedPage, low_confidence_threshold: float = 0.6
    ) -> list[NormalizedBlock]:
        """Normalize a ProcessedPage to unified blocks.

        ``low_confidence_threshold`` is forwarded to
        :meth:`normalize_ocr_result` so blocks derived from a low-quality
        scan page carry the audit flag end-to-end.
        """
        if page.ocr_result:
            return self.normalize_ocr_result(
                page.ocr_result,
                page.page_number,
                low_confidence_threshold=low_confidence_threshold,
            )
        elif page.native_text.strip():
            return [
                NormalizedBlock(
                    block_type=BlockType.PARAGRAPH,
                    page=page.page_number,
                    raw_text=page.native_text,
                    normalized_text=normalize_text(page.native_text, self.config),
                    source="pdf_text",
                    confidence=1.0,
                )
            ]
        return []

    def validate_block(self, block: NormalizedBlock) -> dict[str, Any]:
        """Validate a normalized block for issues.

        Returns:
            Dict with: valid (bool), issues (list), suspicious (list)
        """
        result: dict[str, Any] = {"valid": True, "issues": [], "suspicious": []}

        if block.confidence < 0.7:
            result["issues"].append(f"Low confidence: {block.confidence:.2f}")
            result["valid"] = False

        suspicious = check_suspicious_content(block.normalized_text)
        if suspicious:
            result["suspicious"].extend(suspicious)
            result["issues"].append(f"Suspicious OCR: {', '.join(suspicious)}")
            result["valid"] = False

        if self.config.validate_article_numbers:
            article_nums = re.findall(r"Điều\s+(\d+)", block.normalized_text)
            for num_str in article_nums:
                try:
                    num = int(num_str)
                    if num < 1 or num > 10000:
                        result["issues"].append(f"Suspicious article number: Điều {num_str}")
                except ValueError:
                    result["issues"].append(f"Invalid article number: Điều {num_str}")
                    result["valid"] = False

        if self.config.validate_dates:
            for date_str in DATE_PATTERN.findall(block.normalized_text):
                # Filter out obviously wrong dates
                if not re.search(r"\d{4}", date_str):
                    result["issues"].append(f"Suspicious date: {date_str}")
                    result["valid"] = False

        return result

    def create_unified_document(self, pages: list[ProcessedPage]) -> list[NormalizedBlock]:
        """Build unified document blocks from processed pages."""
        all_blocks: list[NormalizedBlock] = []
        for page in pages:
            all_blocks.extend(self.normalize_processed_page(page))
        return all_blocks


class RuleBasedValidator:
    """Rule-based validator for legal document content.

    Per docs/pdf_processing_pipeline.md Section 10:
    - Validate Điều/Khoản numbers
    - Flag suspicious OCR content
    - Extract statistics (dates, money, percentages)

    Usage:
        validator = RuleBasedValidator()
        report = validator.validate_text(text)
    """

    def __init__(self):
        self.article_re = re.compile(r"Điều\s+(\d+)")
        self.clause_re = re.compile(r"Khoản\s+(\d+)")
        self.point_re = re.compile(r"Điểm\s+([a-zđ])", re.IGNORECASE)
        self.date_re = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
        self.money_re = re.compile(r"[\d.,]+\s*(đồng|vnđ)", re.IGNORECASE)
        self.percent_re = re.compile(r"\d+\s*%|\d+ phần trăm", re.IGNORECASE)
        # OCR confusion: l, I, O, S confused with digits
        self.suspicious_chars = re.compile(r"[l|i|][0-9]|O[0-9]|S[0-9]|[0-9]l\b|[0-9]I\b")

    def validate_text(self, text: str) -> dict[str, Any]:
        """Validate text and extract statistics.

        Returns:
            Dict with: valid, issues, suspicious, statistics
        """
        articles = self.article_re.findall(text)
        clauses = self.clause_re.findall(text)
        points = self.point_re.findall(text)
        dates = self.date_re.findall(text)
        money = self.money_re.findall(text)
        percents = self.percent_re.findall(text)

        result: dict[str, Any] = {
            "valid": True,
            "issues": [],
            "suspicious": [],
            "statistics": {
                "articles": len(articles),
                "clauses": len(clauses),
                "points": len(points),
                "dates": len(dates),
                "money_mentions": len(money),
                "percent_mentions": len(percents),
            },
        }

        if self.suspicious_chars.search(text):
            result["suspicious"].append("suspicious_characters")
            result["valid"] = False

        for num_str in articles:
            try:
                if int(num_str) > 10000:
                    result["issues"].append(f"Invalid article number: Điều {num_str}")
            except ValueError:
                result["issues"].append(f"Invalid article number: Điều {num_str}")

        return result

    def validate_block(self, block: NormalizedBlock) -> dict[str, Any]:
        """Validate a normalized block."""
        text = block.normalized_text
        result = self.validate_text(text)

        if block.confidence < 0.7:
            result["issues"].append(f"Low confidence: {block.confidence:.2f}")
            result["valid"] = False

        # Suspicious characters check
        if self.suspicious_chars.search(text):
            result["suspicious"].append("suspicious_characters")

        return result

    def validate_document(self, blocks: list[NormalizedBlock]) -> dict[str, Any]:
        """Validate entire document.

        Returns:
            Dict with: valid, total_blocks, issues_count, suspicious_count, block_reports
        """
        total = len(blocks)
        issues_count = 0
        suspicious_count = 0
        block_reports = []

        for block in blocks:
            block_result = self.validate_block(block)
            if not block_result["valid"]:
                issues_count += 1
            if block_result["suspicious"]:
                suspicious_count += 1
            block_reports.append({
                "page": block.page,
                "block_type": block.block_type.value,
                "valid": block_result["valid"],
                "issues": block_result["issues"],
                "suspicious": block_result["suspicious"],
            })

        return {
            "valid": issues_count == 0,
            "total_blocks": total,
            "issues_count": issues_count,
            "suspicious_count": suspicious_count,
            "block_reports": block_reports,
        }
