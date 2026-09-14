"""Page classifier for PDF documents.

Per docs/pdf_processing_pipeline.md Section 4:
- Classify each page (not whole document)
- Digital: native text layer
- Scan: image only
- Hybrid: mixed text and images

Uses PyMuPDF for native text extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from src.ingestion.pdf_processor.schemas import PageType


# Thresholds from pipeline docs
DIGITAL_TEXT_RATIO_THRESHOLD = 0.5  # If >50% has native text → Digital
SCAN_TEXT_RATIO_THRESHOLD = 0.1  # If <10% has native text → Scan
# Between 10-50% → Hybrid


class PageClassifier:
    """Classifier for determining PDF page type.

    Per docs/pdf_processing_pipeline.md:
    - Classify per page, not whole document
    - Use native text ratio for classification

    Usage:
        classifier = PageClassifier()
        page_type = classifier.classify_page(pdf_page)
    """

    def __init__(self):
        self._import_pymupdf()

    def _import_pymupdf(self) -> None:
        """Import PyMuPDF."""
        try:
            import pymupdf
            self.fitz = pymupdf
        except ImportError:
            raise ImportError(
                "PyMuPDF not installed. Install with: pip install pymupdf"
            )

    def classify_page(
        self,
        page: "pymupdf.Page",
        dpi: int = 72,
    ) -> PageType:
        """Classify a PDF page.

        Args:
            page: PyMuPDF page object
            dpi: DPI for rendering (for hybrid detection)

        Returns:
            PageType: DIGITAL, SCAN, or HYBRID
        """
        # Extract native text
        text = page.get_text("text") or ""
        words = page.get_text("words") or []

        # Calculate text coverage
        text_length = len(text.strip())
        word_count = len(words)

        # Get page dimensions
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        # Estimate text area coverage
        text_area = 0
        for word in words:
            x0, y0, x1, y1 = word[:4]
            text_area += (x1 - x0) * (y1 - y0)

        # Also check for embedded images
        images = page.get_images(full=True)

        # Calculate ratios
        text_ratio = text_area / page_area if page_area > 0 else 0

        # Decision logic
        if text_ratio >= DIGITAL_TEXT_RATIO_THRESHOLD and not images:
            return PageType.DIGITAL
        elif text_ratio <= SCAN_TEXT_RATIO_THRESHOLD or (not words and images):
            return PageType.SCAN
        else:
            return PageType.HYBRID

    def classify_page_from_bytes(
        self,
        pdf_bytes: bytes,
        page_num: int = 0,
    ) -> PageType:
        """Classify a page from PDF bytes.

        Args:
            pdf_bytes: PDF file as bytes
            page_num: 0-based page number

        Returns:
            PageType
        """
        doc = self.fitz.open(stream=pdf_bytes)
        if page_num >= len(doc):
            raise ValueError(f"Page {page_num} does not exist in document")

        page = doc[page_num]
        result = self.classify_page(page)
        doc.close()
        return result

    def classify_all_pages(
        self,
        pdf_bytes: bytes,
    ) -> list[dict]:
        """Classify all pages in a PDF.

        Args:
            pdf_bytes: PDF file as bytes

        Returns:
            List of dicts with page_num, page_type, and metadata
        """
        doc = self.fitz.open(stream=pdf_bytes)
        results = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_type = self.classify_page(page)

            # Additional metadata
            text = page.get_text("text") or ""
            words = page.get_text("words") or []
            images = page.get_images(full=True)

            results.append({
                "page_num": page_num + 1,  # 1-based
                "page_type": page_type,
                "word_count": len(words),
                "image_count": len(images),
                "text_length": len(text.strip()),
            })

        doc.close()
        return results

    def get_page_statistics(
        self,
        page: "fitz.Page",
    ) -> dict:
        """Get detailed statistics for a page.

        Returns:
            Dict with text coverage, image info, etc.
        """
        # Text extraction
        text = page.get_text("text") or ""
        words = page.get_text("words") or []

        # Image extraction
        images = page.get_images(full=True)

        # Page dimensions
        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        # Text area
        text_area = 0
        for word in words:
            x0, y0, x1, y1 = word[:4]
            text_area += (x1 - x0) * (y1 - y0)

        # Text ratio
        text_ratio = text_area / page_area if page_area > 0 else 0

        return {
            "page_area": page_area,
            "text_area": text_area,
            "text_ratio": text_ratio,
            "word_count": len(words),
            "image_count": len(images),
            "has_native_text": len(words) > 0,
            "has_images": len(images) > 0,
            "text_length": len(text.strip()),
        }


class PageClassifierSimple:
    """Simpler page classifier using basic heuristics.

    Use this when PyMuPDF is not available or for quick classification.
    """

    def __init__(
        self,
        digital_threshold: float = DIGITAL_TEXT_RATIO_THRESHOLD,
        scan_threshold: float = SCAN_TEXT_RATIO_THRESHOLD,
    ):
        self.digital_threshold = digital_threshold
        self.scan_threshold = scan_threshold

    def classify_from_text_ratio(
        self,
        text_ratio: float,
        has_images: bool = False,
    ) -> PageType:
        """Classify based on text ratio.

        Args:
            text_ratio: Ratio of text area to page area (0.0 - 1.0)
            has_images: Whether page has embedded images

        Returns:
            PageType
        """
        if text_ratio >= self.digital_threshold and not has_images:
            return PageType.DIGITAL
        elif text_ratio <= self.scan_threshold or (text_ratio < 0.1 and has_images):
            return PageType.SCAN
        else:
            return PageType.HYBRID
