"""PDF processing pipeline.

Processes PDF pages through:
1. Page classification (digital/scan/hybrid) + hybrid text-extract gate
2. Image preprocessing (for scan pages)
3. OCR with RapidOCR + PP-OCRv6 Vietnamese — optional PP-StructureV3 path
4. Table extraction (heuristic grid detection OR PP-Structure)
5. Document normalization (structure, validation, suspicious OCR detection)

Outputs ProcessedDocument with normalized blocks ready for RAG ingestion.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field, replace as dc_replace
from typing import TYPE_CHECKING, Any

import numpy as np

logger = logging.getLogger(__name__)

from src.ingestion.pdf_processor.document_normalizer import (
    DocumentNormalizer,
    NormalizerConfig,
    RuleBasedValidator,
)
from src.ingestion.pdf_processor.image_preprocessor import (
    ImagePreprocessor,
    PreprocessConfig,
    PreprocessMode,
)
from src.ingestion.pdf_processor.ocr_engine import OCRConfig, OCREngine
from src.ingestion.pdf_processor.page_classifier import PageClassifier
from src.ingestion.pdf_processor.pp_structure import (
    PPStructureConfig,
    PPStructureEngine,
)
from src.ingestion.pdf_processor.schemas import (
    BlockType,
    PageType,
    ProcessedDocument,
    ProcessedPage,
)
from src.ingestion.pdf_processor.table_extractor import TableConfig, TableExtractor

if TYPE_CHECKING:
    import pymupdf


@dataclass
class PipelineConfig:
    """Configuration for PDF processing pipeline."""

    # Processing mode
    preprocess_mode: PreprocessMode = PreprocessMode.QUALITY  # DPI 600

    # OCR settings
    ocr_config: OCRConfig = field(default_factory=OCRConfig)
    ocr_min_confidence: float = 0.5

    # Hybrid text-extract gate — pages whose ``pymupdf.Page.get_text()``
    # yields at least ``hybrid_text_threshold`` characters bypass OCR
    # even when the page classifier labelled them SCAN (e.g. a scanned
    # page with a coincidental text layer from the PDF outline).
    # Likewise a page labelled DIGITAL with too little text is forced
    # through OCR (e.g. a cover page that is mostly a stamp/seal image).
    # Set ``hybrid_text_threshold=None`` to disable the override and
    # always trust the page classifier.
    #
    # Override via env var ``OCR_HYBRID_TEXT_THRESHOLD``:
    # * integer (e.g. ``50``) — use that exact threshold
    # * ``""`` (empty) or ``"none"`` — disable the gate
    # * unset — keep the constructor default
    hybrid_text_threshold: int | None = 50

    @classmethod
    def from_env(cls, **overrides: object) -> "PipelineConfig":
        """Build a config picking up env-var overrides.

        Currently recognises:

        * ``OCR_HYBRID_TEXT_THRESHOLD`` — see :attr:`hybrid_text_threshold`.
        * ``OCR_LOW_CONFIDENCE_THRESHOLD`` — float forwarded to
          :class:`OCRConfig.low_confidence_threshold`. Lowering the
          default 0.7 to e.g. 0.5 surfaces more scan pages for the
          audit flag (drives ``section.low_confidence`` end-to-end
          through to ``metadata_json.low_confidence``).

        Pass any keyword args via ``overrides`` to override the env
        values directly (used by bench scripts).
        """
        env_threshold = os.environ.get("OCR_HYBRID_TEXT_THRESHOLD")
        if env_threshold is not None:
            normalised = env_threshold.strip().lower()
            if normalised in ("", "none", "null", "off"):
                overrides.setdefault("hybrid_text_threshold", None)
            else:
                overrides.setdefault(
                    "hybrid_text_threshold", int(env_threshold)
                )
        env_low_conf = os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD")
        if env_low_conf is not None:
            cfg = overrides.pop("ocr_config", None) or OCRConfig()
            cfg = dc_replace(
                cfg, low_confidence_threshold=float(env_low_conf)
            )
            overrides["ocr_config"] = cfg
        return cls(**overrides)

    # DPI strategy: the cover/legal-numbering page (page 1) is rendered at
    # ``cover_dpi`` to keep document_number/issued_by/issuer signatures
    # legible. Body pages drop to ``body_dpi`` because the body text is
    # large enough that lower DPI still yields accurate OCR while
    # halving the per-page compute. The **last** page is also bumped
    # back to a high DPI by default (``last_page_dpi``), because legal
    # documents routinely carry signatures, stamps, and approver names
    # on the final page and reducing those to 300 DPI degrades the most
    # critical metadata capture. Set ``last_page_dpi=None`` to disable
    # the last-page bump and apply ``body_dpi`` uniformly.
    cover_dpi: int = 600
    body_dpi: int = 300
    last_page_dpi: int | None = 600

    # Table extraction
    detect_tables: bool = True
    table_config: TableConfig = field(default_factory=TableConfig)
    use_pp_structure: bool = False
    pp_structure_config: PPStructureConfig | None = None

    # Normalization
    normalizer_config: NormalizerConfig = field(default_factory=NormalizerConfig)

    # VLM review (optional)
    vlm_enabled: bool = False
    vlm_review_threshold: float = 0.7


def render_page_to_image(page: pymupdf.Page, dpi: int) -> np.ndarray:
    """Render a PDF page to RGB numpy array."""
    import pymupdf

    mat = pymupdf.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = img[:, :, :3]
    elif pix.n == 1:
        img = np.stack([img] * 3, axis=-1)
    return img


class PDFProcessingPipeline:
    """Main pipeline for processing PDF documents.

    Per docs/pdf_processing_pipeline.md:
    - Page classification: Digital / Scan / Hybrid
    - Hybrid text-extract gate: skip OCR when text layer ≥ threshold
    - Image preprocessing: DPI 600, Binary Threshold 140
    - OCR: RapidOCR + PP-OCRv6 Vietnamese ONNX
    - Table extraction: heuristic grid detection OR layout-aware
    - Document normalization + rule-based validation

    Usage:
        pipeline = PDFProcessingPipeline()
        result = pipeline.process_pdf(pdf_bytes, document_id="...", filename="...")
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()

        self.page_classifier = PageClassifier()
        self.image_preprocessor = ImagePreprocessor(
            PreprocessConfig(dpi=600, binary_threshold=140)
        )
        self.ocr_engine = OCREngine(self.config.ocr_config)
        self.pp_engine: PPStructureEngine | None = None
        if self.config.use_pp_structure:
            self.pp_engine = PPStructureEngine(
                self.config.pp_structure_config or PPStructureConfig()
            )
        self.table_extractor = TableExtractor(self.config.table_config)
        if self.pp_engine is not None:
            self.table_extractor.set_pp_structure(self.pp_engine)
            # Match the heuristic detector's gating flag.
            self.table_extractor.config.use_pp_structure = True
        self.normalizer = DocumentNormalizer(self.config.normalizer_config)
        self.validator = RuleBasedValidator()

    def process_pdf(
        self,
        pdf_bytes: bytes,
        document_id: str,
        filename: str = "",
        dpi: int = 600,
    ) -> ProcessedDocument:
        """Process a complete PDF document.

        Args:
            pdf_bytes: PDF file content
            document_id: Unique document identifier
            filename: Original filename
            dpi: DPI for the first page (the cover/legal-numbering page that
                holds document_number, issued_by, issued_date and the
                signer). Subsequent pages render at ``dpi // 2`` because
                the body text is large enough that lower DPI still yields
                accurate OCR while halving the per-page compute.

        Returns:
            ProcessedDocument with all pages and normalized blocks
        """
        import pymupdf

        doc = pymupdf.open(stream=pdf_bytes)

        document = ProcessedDocument(
            document_id=document_id,
            filename=filename,
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
            total_pages=len(doc),
        )

        body_dpi = self.config.body_dpi or max(150, dpi // 2)
        cover_dpi = self.config.cover_dpi or dpi
        # ``None`` means "disable the last-page bump" (e.g. for documents
        # that don't have signatures/stamps on the last page — short
        # invoices, memos). The default pipeline config sets it to
        # ``cover_dpi`` because legal documents are the dominant ingest.
        last_page_dpi = self.config.last_page_dpi
        total_pages = len(doc)
        for page_num in range(total_pages):
            page = doc[page_num]
            # Multi-tier DPI strategy: cover (page 1) + last page (+ optional
            # future annexes) keep the requested DPI; body pages drop to
            # ``body_dpi`` for the per-page compute saving. See
            # ``_resolve_page_dpi`` for the full policy.
            page_dpi = self._resolve_page_dpi(
                page_num,
                total_pages=total_pages,
                cover_dpi=cover_dpi,
                body_dpi=body_dpi,
                last_page_dpi=last_page_dpi,
            )
            processed_page = self._process_page(page, page_num + 1, page_dpi)

            document.pages.append(processed_page)

            if processed_page.page_type == PageType.DIGITAL:
                document.digital_pages += 1
            elif processed_page.page_type == PageType.SCAN:
                document.scan_pages += 1
            else:
                document.hybrid_pages += 1

        doc.close()

        # Normalize all pages into unified blocks
        document.blocks = self.normalizer.create_unified_document(document.pages)

        return document

    @staticmethod
    def _resolve_page_dpi(
        page_num: int,
        *,
        total_pages: int,
        cover_dpi: int,
        body_dpi: int,
        last_page_dpi: int | None,
    ) -> int:
        """Pick the rendering DPI for a single page.

        Policy:

        * **First page** (``page_num == 0``) always uses ``cover_dpi``.
          Cover/legal-numbering pages must remain legible for
          ``document_number``/``issued_by`` extraction.
        * **Last page** (``page_num == total_pages - 1``) uses
          ``last_page_dpi`` if it is not ``None``; otherwise the last
          page falls back to ``body_dpi``. The default pipeline keeps
          the last page at ``cover_dpi`` so signatures and approval
          stamps stay readable — a 300-DPI downscale on those pages
          degrades the most critical metadata capture.
        * All other pages use ``body_dpi`` to halve per-page compute.
        * ``total_pages == 1`` returns ``cover_dpi``: the single page
          *is* the cover and the last page simultaneously; the rule
          combines naturally.

        Extracted from the per-page loop so the policy is auditable in
        isolation and the cover / last / body tiers can be tested
        without spinning up the full pipeline + RapidOCR.
        """
        if total_pages <= 0:
            return body_dpi
        if page_num == 0:
            return cover_dpi
        if page_num == total_pages - 1 and last_page_dpi is not None:
            return last_page_dpi
        return body_dpi

    def _process_page(
        self,
        page: pymupdf.Page,
        page_num: int,
        dpi: int,
    ) -> ProcessedPage:
        """Classify and process a single page.

        Hybrid gate (text-extract-first): pages whose
        ``page.get_text()`` already returns enough characters (>= 
        ``hybrid_text_threshold``) bypass OCR regardless of what the
        page classifier said. The override applies in three directions:

        * ``SCAN`` → ``DIGITAL`` when text ≥ threshold (PDF had a
          text layer despite the image-only render).
        * ``HYBRID`` → ``DIGITAL`` when text ≥ threshold (the OCR
          cost was wasted on a page that already extracted cleanly).
        * ``DIGITAL`` → ``SCAN`` when text < threshold (cover/stamp
          page that is mostly an image).

        The override is logged so bench scripts can verify the gate is
        firing (or not) on a per-page basis.
        """
        page_type = self.page_classifier.classify_page(page)
        threshold = self.config.hybrid_text_threshold

        if threshold is not None:
            native_len = len((page.get_text("text") or "").strip())
            if (
                page_type in (PageType.SCAN, PageType.HYBRID)
                and native_len >= threshold
            ):
                logger.info(
                    "hybrid_gate_override page=%d %s->digital native_chars=%d",
                    page_num,
                    page_type.value,
                    native_len,
                )
                page_type = PageType.DIGITAL
            elif page_type == PageType.DIGITAL and native_len < threshold:
                logger.info(
                    "hybrid_gate_override page=%d digital->scan native_chars=%d",
                    page_num,
                    native_len,
                )
                page_type = PageType.SCAN

        processed_page = ProcessedPage(
            page_number=page_num,
            page_type=page_type,
        )

        if page_type == PageType.DIGITAL:
            self._process_digital_page(page, processed_page)
        elif page_type == PageType.SCAN:
            self._process_scan_page(page, processed_page, dpi)
        else:
            self._process_hybrid_page(page, processed_page, dpi)

        return processed_page

    def _process_digital_page(
        self, page: pymupdf.Page, processed_page: ProcessedPage
    ) -> None:
        """Process a digital (native text) page."""
        from src.ingestion.pdf_processor.schemas import (
            BoundingBox,
            OCRBlock,
            OCRResult,
        )

        blocks = page.get_text("dict")["blocks"]
        native_text = page.get_text("text") or ""

        ocr_result = OCRResult(
            page=processed_page.page_number,
            page_type=PageType.DIGITAL,
            raw_text=native_text,
            average_confidence=1.0,
            needs_review=False,
        )

        for block in blocks:
            if block.get("type") != 0:  # Not a text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span.get("bbox")
                    if not bbox:
                        continue
                    ocr_result.blocks.append(
                        OCRBlock(
                            block_type=BlockType.PARAGRAPH,
                            text=span.get("text", ""),
                            bbox=BoundingBox(
                                x0=bbox[0], y0=bbox[1],
                                x1=bbox[2], y1=bbox[3],
                            ),
                            page=processed_page.page_number,
                            confidence=1.0,
                        )
                    )

        processed_page.native_text = native_text
        processed_page.ocr_result = ocr_result

    def _process_scan_page(
        self, page: pymupdf.Page, processed_page: ProcessedPage, dpi: int
    ) -> None:
        """Process a scan (image-only) page.

        ``dpi`` is the page-level rendering resolution requested by
        ``_resolve_page_dpi`` (600 for the cover, 300 for the body, etc.).
        Scanned pages have no native text to extract, so the cover/last
        DPI bump only matters for OCR quality — and OCR model behaviour
        is best around 150-200 DPI per ``data/ocr/outputs/REPORT.md``
        (the 300/600 sweep showed diacritic recovery degrades at very
        high DPI because more noisy text segments compete for the
        dictionary). Clamp the effective scan DPI to ``body_dpi`` so the
        cover/last bump does not push scanned pages above the sweet spot.
        """
        scan_dpi = min(dpi, self.config.body_dpi or 200)
        img = render_page_to_image(page, dpi=scan_dpi)

        # Preprocess for OCR
        preprocessed = self.image_preprocessor.preprocess(img, page_num=processed_page.page_number)

        # Choose backend: PP-StructureV3 (layout + tables) or plain OCREngine.
        if self.pp_engine is not None:
            ocr_result = self.pp_engine.process(
                preprocessed["image"],
                page_num=processed_page.page_number,
            )
        else:
            ocr_result = self.ocr_engine.recognize(
                preprocessed["image"],
                page_num=processed_page.page_number,
                preprocessed=True,
            )

        # Filter by confidence (PP-Structure blocks already carry per-region scores)
        filtered = [b for b in ocr_result.blocks if b.confidence >= self.config.ocr_min_confidence]
        ocr_result.blocks = filtered
        ocr_result.average_confidence = (
            sum(b.confidence for b in filtered) / len(filtered) if filtered else 0.0
        )

        # Extract tables. When PP-Structure is on, the engine already
        # returned tables inside ``ocr_result.tables``; only run the
        # heuristic if the table list is empty and the feature flag is set.
        if self.config.detect_tables and not ocr_result.tables:
            tables = self.table_extractor.extract_tables(
                preprocessed["image"], page_num=processed_page.page_number
            )
            ocr_result.tables.extend(tables)

        processed_page.ocr_result = ocr_result

    def _process_hybrid_page(
        self, page: pymupdf.Page, processed_page: ProcessedPage, dpi: int
    ) -> None:
        """Process a hybrid (mixed text and image) page.

        Hybrid pages have a partial text layer, but the image portion
        still goes through OCR. Same DPI clamp as SCAN pages applies:
        ``body_dpi`` (≤200) is the OCR sweet spot per REPORT.md.
        """
        scan_dpi = min(dpi, self.config.body_dpi or 200)
        native_text = page.get_text("text") or ""
        img = render_page_to_image(page, dpi=scan_dpi)

        preprocessed = self.image_preprocessor.preprocess(img, page_num=processed_page.page_number)
        if self.pp_engine is not None:
            ocr_result = self.pp_engine.process(
                preprocessed["image"],
                page_num=processed_page.page_number,
            )
        else:
            ocr_result = self.ocr_engine.recognize(
                preprocessed["image"],
                page_num=processed_page.page_number,
            )

        filtered = [b for b in ocr_result.blocks if b.confidence >= self.config.ocr_min_confidence]
        ocr_result.blocks = filtered
        ocr_result.average_confidence = (
            sum(b.confidence for b in filtered) / len(filtered) if filtered else 0.0
        )

        if self.config.detect_tables and not ocr_result.tables:
            tables = self.table_extractor.extract_tables(
                preprocessed["image"], page_num=processed_page.page_number
            )
            ocr_result.tables.extend(tables)

        processed_page.native_text = native_text
        processed_page.ocr_result = ocr_result

    def validate_document(self, document: ProcessedDocument) -> dict[str, Any]:
        """Validate processed document.

        Checks for:
        - Low OCR confidence pages (need VLM review)
        - Suspicious characters in OCR output
        - Invalid article numbers, dates

        Returns:
            Validation report dict
        """
        report: dict[str, Any] = {
            "valid": True,
            "pages": [],
            "issues": [],
            "warnings": [],
            "needs_vlm_review": False,
        }

        for page in document.pages:
            page_report = {
                "page": page.page_number,
                "type": page.page_type.value,
                "issues": [],
                "warnings": [],
            }

            if page.ocr_result:
                if page.ocr_result.average_confidence < self.config.vlm_review_threshold:
                    page_report["issues"].append(
                        f"Low confidence: {page.ocr_result.average_confidence:.2f}"
                    )
                    report["needs_vlm_review"] = True
                    report["valid"] = False

                page_report["warnings"] = page.ocr_result.warnings
                report["warnings"].extend(page.ocr_result.warnings)

                if self.config.detect_tables and page.ocr_result.tables:
                    page_report["tables_found"] = len(page.ocr_result.tables)

            report["pages"].append(page_report)

        return report

    def get_stats(self, document: ProcessedDocument) -> dict[str, Any]:
        """Get processing statistics for monitoring/debugging.

        Includes the low-confidence page list (pages whose
        ``ocr_result.average_confidence`` fell below the configured
        ``ocr_low_confidence_threshold``). Operators consult this list
        to decide whether a scan needs VLM review or human approval.
        """
        total_blocks = sum(
            len(p.ocr_result.blocks) if p.ocr_result else 0
            for p in document.pages
        )
        total_tables = sum(
            len(p.ocr_result.tables) if p.ocr_result else 0
            for p in document.pages
        )

        confidences = [
            p.ocr_result.average_confidence
            for p in document.pages if p.ocr_result
        ]
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0

        low_conf_threshold = float(
            getattr(self.config, "ocr_config", None)
            and self.config.ocr_config.low_confidence_threshold
            or 0.6
        )
        low_conf_numbers = [
            p.page_number
            for p in document.pages
            if p.ocr_result is not None
            and p.ocr_result.average_confidence < low_conf_threshold
        ]

        # Mirror the stats back onto the document so downstream readers
        # (bench scripts, ingestion drivers) can read them without
        # re-iterating page-level ocr_results.
        document.low_confidence_page_count = len(low_conf_numbers)
        document.low_confidence_page_numbers = low_conf_numbers
        document.needs_review = bool(low_conf_numbers)

        return {
            "total_pages": document.total_pages,
            "digital_pages": document.digital_pages,
            "scan_pages": document.scan_pages,
            "hybrid_pages": document.hybrid_pages,
            "total_blocks": total_blocks,
            "total_tables": total_tables,
            "average_confidence": avg_confidence,
            "needs_review": document.needs_review,
            "low_confidence_page_count": len(low_conf_numbers),
            "low_confidence_page_numbers": low_conf_numbers,
            "low_confidence_threshold": low_conf_threshold,
        }

    async def vlm_review(self, raw_ocr: str, ocr_confidence: float) -> dict[str, Any]:
        """Perform VLM-assisted review of OCR results.

        Per docs/pdf_processing_pipeline.md Section 11:
        - Use VLM only as fallback validation layer
        - Pass original image crop + raw OCR + confidence

        Args:
            raw_ocr: OCR text to review
            ocr_confidence: Original confidence score

        Returns:
            Review result with corrections
        """
        if not self.config.vlm_enabled:
            return {
                "raw_ocr": raw_ocr,
                "corrected": raw_ocr,
                "review_method": "disabled",
                "confidence": ocr_confidence,
            }

        # Placeholder - integrate with actual VLM service when ready
        return {
            "raw_ocr": raw_ocr,
            "corrected": raw_ocr,
            "review_method": "placeholder",
            "confidence": ocr_confidence,
        }

    def warmup(self) -> None:
        """Warmup the OCR engine for faster first use."""
        self.ocr_engine.warmup()
        if self.pp_engine is not None:
            self.pp_engine.warmup()
