"""Document parser for RAG ingestion.

Supports:
- PDF (via pypdf with optional pdfplumber table extraction)
- DOCX
- TXT
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from src.domain.schemas import ParsedBlock


class ParseError(ValueError):
    pass


# Filename suffixes that flag a PDF as containing structured tables that
# must be preserved across the RAG pipeline. The exact suffix is kept in
# sync with ``scripts/ingest_with_timing.py::_TABLE_STEM_SUFFIXES`` so
# that the parser and the ingestion driver stay aligned on which files
# are "table test variants".
_TABLE_STEM_SUFFIXES = ("-table", "_table", "-bang", "_bang")


def looks_like_table_variant(filename: str) -> bool:
    """Return True if ``filename`` carries a table-test suffix.

    Pure filename check — no dependency on file content. Used by the auto
    parser backend to route ``<n>-table.pdf`` files through the table-aware
    parser even when the PDF is born-digital (i.e. no OCR needed).
    """
    stem = Path(filename).stem.lower()
    return any(stem.endswith(suf) for suf in _TABLE_STEM_SUFFIXES)


class DocumentParser:
    """Parse documents into unified ParsedBlock list.

    All parsers produce the same ParsedBlock schema, which is the unified
    format used throughout the RAG pipeline.
    """

    def __init__(
        self,
        parser_backend: str = "auto",
        docling_enabled: bool = True,
        ocr_enabled: bool = True,
        min_ocr_confidence: float = 0.5,
        ocr_languages: list[str] | None = None,
        ocr_gpu: bool = False,
        ocr_batch_size: int = 1,
        ocr_workers: int = 4,
        ocr_low_confidence_threshold: float = 0.5,
        ocr_hybrid_text_threshold: int | None = 50,
        preprocess_mode: str = "quality",
        preprocess_dpi: int = 600,
        preprocess_binary_threshold: int = 140,
        preprocess_denoise: bool = True,
        preprocess_sharpen: bool = True,
        detect_tables: bool = True,
        vlm_enabled: bool = False,
        vlm_review_threshold: float = 0.7,
        ocr_engine_type: str = "rapidocr_vi",
        use_pp_structure: bool = False,
        pp_structure_lang: str = "vi",
        pp_structure_text_det_limit_side_len: int = 1536,
        pp_structure_layout_threshold: float = 0.5,
    ):
        self.parser_backend = parser_backend
        self.docling_enabled = docling_enabled
        self.ocr_enabled = ocr_enabled
        self.min_ocr_confidence = min_ocr_confidence
        self.ocr_languages = list(ocr_languages or ["vi", "en"])
        self.ocr_gpu = bool(ocr_gpu)
        self.ocr_batch_size = int(ocr_batch_size)
        self.ocr_workers = int(ocr_workers)
        # Default lowered from 0.7 → 0.5 (2026-09-06 metadata cleanup).
        # Lower threshold surfaces more scan pages for the audit flag, which
        # routes them through ``extract_sections(ocr_mode=True)`` semantic
        # chunking fallback instead of regex heading detection on noisy OCR.
        # Operators can still override per ingest via env var or constructor.
        self.ocr_low_confidence_threshold = float(ocr_low_confidence_threshold)
        # ``None`` disables the hybrid text-extract gate (legacy
        # "always trust page classifier" behaviour); 0 also disables
        # by convention. Otherwise pages with at least that many
        # native chars bypass OCR even when labelled SCAN/HYBRID.
        if ocr_hybrid_text_threshold is None:
            self.ocr_hybrid_text_threshold: int | None = None
        else:
            self.ocr_hybrid_text_threshold = max(0, int(ocr_hybrid_text_threshold))
        self.preprocess_mode = preprocess_mode
        self.preprocess_dpi = int(preprocess_dpi)
        self.preprocess_binary_threshold = int(preprocess_binary_threshold)
        self.preprocess_denoise = bool(preprocess_denoise)
        self.preprocess_sharpen = bool(preprocess_sharpen)
        self.detect_tables = bool(detect_tables)
        self.vlm_enabled = bool(vlm_enabled)
        self.vlm_review_threshold = float(vlm_review_threshold)
        self.ocr_engine_type = ocr_engine_type
        self.use_pp_structure = bool(use_pp_structure)
        self.pp_structure_lang = pp_structure_lang
        self.pp_structure_text_det_limit_side_len = int(
            pp_structure_text_det_limit_side_len
        )
        self.pp_structure_layout_threshold = float(pp_structure_layout_threshold)

    @classmethod
    def from_env(cls, **overrides: object) -> "DocumentParser":
        """Build a parser using env-var overrides.

        Recognised env vars (all optional):

        * ``OCR_LOW_CONFIDENCE_THRESHOLD`` — float forwarded to
          ``ocr_low_confidence_threshold``. Default 0.5; set lower
          (e.g. 0.4) to surface more pages as low-confidence for
          audit; set higher (e.g. 0.7) to keep permissive.

        Pass any keyword args via ``overrides`` to override the env
        values directly (used by bench scripts).
        """
        env_low_conf = os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD")
        if env_low_conf is not None:
            try:
                overrides.setdefault(
                    "ocr_low_confidence_threshold", float(env_low_conf)
                )
            except ValueError:
                # Tolerate a malformed value by falling back to the
                # constructor default rather than crashing the parser.
                pass
        return cls(**overrides)

    def parse_to_markdown(self, filename: str, content: bytes) -> tuple[str, list[str]]:
        """Parse document directly into a unified Markdown text representation."""
        blocks, warnings = self.parse(filename, content)
        markdown_lines = []
        current_page = None

        for block in blocks:
            if block.page is not None and block.page != current_page:
                current_page = block.page
                markdown_lines.append(f"\n<!-- Page {current_page} -->\n")
            markdown_lines.append(block.text)

        markdown_text = "\n\n".join(markdown_lines).strip()
        return markdown_text, warnings

    def parse(
        self,
        filename: str,
        content: bytes,
        *,
        override_use_pp_structure: bool | None = None,
    ) -> tuple[list[ParsedBlock], list[str]]:
        extension = Path(filename).suffix.lower()
        if extension == ".pdf":
            return self._parse_pdf(content, filename=filename, override_use_pp_structure=override_use_pp_structure)
        if extension == ".docx":
            return self._parse_docx(content)
        if extension == ".txt":
            return self._parse_text(content)
        raise ParseError(f"Không hỗ trợ định dạng {extension}")

    def _parse_pdf(
        self,
        content: bytes,
        filename: str = "",
        *,
        override_use_pp_structure: bool | None = None,
    ) -> tuple[list[ParsedBlock], list[str]]:
        """Parse PDF using a digital-first path.

        Routes:
        * ``pypdf_table`` — pypdf text + pdfplumber table extraction. Used
          for filenames flagged as table variants (e.g. ``2048-table.pdf``)
          and for any other digital PDF when the operator explicitly opts in.
        * ``pypdf`` — plain pypdf text extraction. Fast, no OCR.
        * any other backend with OCR enabled — full PDF processor + EasyOCR
          (slow; reserved for scanned/hybrid PDFs).
        """
        # An explicit pypdf backend is useful for born-digital PDFs and keeps
        # large OCR models out of the ingestion process. It still parses the
        # real PDF text layer; no test double or synthetic content is involved.
        if self.parser_backend == "pypdf":
            return self._parse_pdf_simple(content)

        # Table-aware backend: native text layer + structured tables. This
        # is the right path for files flagged with ``-table`` / ``-bang`` and
        # for any document whose value comes from the table structure rather
        # than the prose.
        if self.parser_backend == "pypdf_table" or (
            self.parser_backend == "auto" and filename and looks_like_table_variant(filename)
        ):
            return self._parse_pdf_with_tables(content, filename=filename)

        if self.ocr_enabled:
            try:
                return self._parse_with_pdf_processor(
                    content,
                    filename=filename,
                    override_use_pp_structure=override_use_pp_structure,
                )
            except Exception as exc:
                # Fall back to simple pypdf if PDF processor fails
                warnings = [f"PDF processor failed ({exc}); falling back to pypdf."]
                return self._parse_pdf_simple(content, warnings=warnings)

        # No OCR: use simple pypdf parser
        return self._parse_pdf_simple(content)

    def _parse_with_pdf_processor(
        self,
        content: bytes,
        filename: str = "",
        *,
        override_use_pp_structure: bool | None = None,
    ) -> tuple[list[ParsedBlock], list[str]]:
        """Parse PDF using the unified PDF processor."""
        from src.ingestion.pdf_processor import (
            ImagePreprocessor,
            OCRConfig,
            OCREngine,
            PDFProcessingPipeline,
            PPStructureConfig,
            PipelineConfig,
            PreprocessConfig,
            PreprocessMode,
            TableConfig,
            TableExtractor,
        )
        from src.ingestion.pdf_processor.document_normalizer import (
            DocumentNormalizer,
            NormalizerConfig,
        )

        # Build a PipelineConfig that mirrors RAGSettings exactly. Anything
        # missing here means operators are still relying on hard-coded
        # defaults from a 600 DPI legal-document pipeline, which is wrong
        # for, say, a low-DPI fast ingestion run.
        # Derive use_pp_structure: command-level override wins; otherwise fall
        # back to the RAGSettings default.
        effective_pp_structure = (
            override_use_pp_structure
            if override_use_pp_structure is not None
            else self.use_pp_structure
        )
        preprocess_mode = (
            PreprocessMode(self.preprocess_mode)
            if isinstance(self.preprocess_mode, str)
            else self.preprocess_mode
        )
        ocr_config = OCRConfig(
            languages=self.ocr_languages,
            gpu=self.ocr_gpu,
            batch_size=self.ocr_batch_size,
            workers=self.ocr_workers,
            min_confidence=self.min_ocr_confidence,
            low_confidence_threshold=self.ocr_low_confidence_threshold,
            detect_tables=self.detect_tables,
            lang=self.ocr_languages[0] if self.ocr_languages else "vi",
        )
        preprocess_config = PreprocessConfig(
            dpi=self.preprocess_dpi,
            binary_threshold=self.preprocess_binary_threshold,
            denoise=self.preprocess_denoise,
            sharpen=self.preprocess_sharpen,
        )
        table_config = TableConfig(
            use_pp_structure=effective_pp_structure,
        )
        pp_structure_config = None
        if effective_pp_structure:
            pp_structure_config = PPStructureConfig(
                lang=self.pp_structure_lang,
                gpu=self.ocr_gpu,
                layout_threshold=self.pp_structure_layout_threshold,
                text_det_limit_side_len=self.pp_structure_text_det_limit_side_len,
            )
        pipeline_config = PipelineConfig(
            preprocess_mode=preprocess_mode,
            ocr_config=ocr_config,
            ocr_min_confidence=self.min_ocr_confidence,
            hybrid_text_threshold=self.ocr_hybrid_text_threshold,
            detect_tables=self.detect_tables,
            table_config=table_config,
            use_pp_structure=effective_pp_structure,
            pp_structure_config=pp_structure_config,
            normalizer_config=NormalizerConfig(),
            vlm_enabled=self.vlm_enabled,
            vlm_review_threshold=self.vlm_review_threshold,
        )
        pipeline = PDFProcessingPipeline(pipeline_config)
        # Override the preprocessor to honor settings.dpi / threshold rather
        # than the hard-coded defaults inside PDFProcessingPipeline.__init__.
        pipeline.image_preprocessor = ImagePreprocessor(preprocess_config)

        doc = pipeline.process_pdf(
            pdf_bytes=content,
            document_id="ingest",
            filename=filename or "document.pdf",
            dpi=self.preprocess_dpi,
        )

        blocks = self._convert_processed_doc(doc)
        warnings = []

        if doc.has_scan_content:
            warnings.append(
                "Tài liệu có trang scan; đã dùng OCR. Data owner cần kiểm duyệt kỹ nội dung và số trang."
            )

        if not blocks:
            raise ParseError("Không trích xuất được văn bản từ PDF.")

        return blocks, warnings

    def _convert_processed_doc(self, doc) -> list[ParsedBlock]:
        """Convert ProcessedDocument to ParsedBlock list."""
        blocks: list[ParsedBlock] = []
        block_index = 0

        for page in doc.pages:
            page_num = page.page_number

            # Add native text blocks (digital pages)
            if page.native_text and page.native_text.strip():
                blocks.append(
                    ParsedBlock.from_native_text(
                        text=page.native_text,
                        page=page_num,
                        block_index=block_index,
                    )
                )
                block_index += 1

            # Add OCR blocks (scan/hybrid pages)
            if page.ocr_result:
                # Carry the page's average confidence + low_confidence
                # flag through to every block so downstream
                # ``extract_sections(ocr_mode=True)`` can route fragile
                # blocks to a semantic-chunking fallback instead of
                # trying to recover heading structure from noise.
                page_avg_conf = page.ocr_result.average_confidence
                is_low_conf_page = (
                    page_avg_conf < self.ocr_low_confidence_threshold
                )
                for ocr_block in page.ocr_result.blocks:
                    # Filter by confidence
                    if ocr_block.confidence < self.min_ocr_confidence:
                        continue
                    if len(ocr_block.text.strip()) < 5:
                        continue

                    blocks.append(
                        ParsedBlock.from_ocr_block(
                            ocr_block=ocr_block,
                            block_index=block_index,
                            page_avg_confidence=page_avg_conf,
                            low_confidence_threshold=self.ocr_low_confidence_threshold,
                        )
                    )
                    block_index += 1

        return blocks

    def _parse_pdf_with_tables(
        self, content: bytes, filename: str = ""
    ) -> tuple[list[ParsedBlock], list[str]]:
        """Parse a digital PDF while preserving tables as Markdown.

        Steps:
        1. Extract per-page text with ``pypdf``.
        2. For each page, run ``pdfplumber.extract_tables()`` and render any
           non-empty table as Markdown. The Markdown block is inserted after
           the page's text block so the chunker/RAG retrieves the table in
           the same semantic unit as the surrounding page.
        3. Pages that yield no tables fall back to plain text — same as
           ``_parse_pdf_simple``.

        This path is digital-only: it assumes the PDF has a text layer. For
        scanned PDFs the operator must switch to a backend with OCR enabled.
        """
        try:
            import pdfplumber  # noqa: F401  (imported lazily so the module
            # remains optional for installs that don't need tables)
        except ImportError as exc:
            raise ParseError(
                "pdfplumber chưa được cài đặt; không thể dùng backend pypdf_table."
            ) from exc

        warnings: list[str] = []
        reader = PdfReader(io.BytesIO(content))
        blocks: list[ParsedBlock] = []
        block_index = 0
        page_count = len(reader.pages)

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page_index, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                tables = self._extract_page_tables(pdf.pages[page_index - 1])

                if page_text:
                    blocks.append(
                        ParsedBlock.from_native_text(
                            text=page_text,
                            page=page_index,
                            block_index=block_index,
                        )
                    )
                    block_index += 1

                for table_md in tables:
                    if not table_md.strip():
                        continue
                    blocks.append(
                        ParsedBlock.from_native_text(
                            text=table_md,
                            page=page_index,
                            block_index=block_index,
                        ).model_copy(update={"source": "table_parser", "block_type": "table"})
                    )
                    block_index += 1

        if not blocks:
            raise ParseError("Không trích xuất được văn bản từ PDF; cần OCR hoặc kiểm tra tệp.")

        table_blocks = [b for b in blocks if b.source == "table_parser"]
        if table_blocks:
            warnings.append(
                f"Đã trích xuất {len(table_blocks)} khối bảng (pdfplumber, dạng Markdown). "
                "Cần kiểm duyệt cấu trúc bảng trước khi dùng cho truy vấn."
            )
        return blocks, warnings

    @staticmethod
    def _extract_page_tables(plumber_page) -> list[str]:
        """Render each non-empty table on a page as a Markdown string.

        Empty rows are collapsed; cells are stripped of newlines so the
        Markdown pipe ``|`` separator is preserved.
        """
        try:
            tables = plumber_page.extract_tables() or []
        except Exception:
            return []

        rendered: list[str] = []
        for table in tables:
            if not table:
                continue
            rows: list[str] = []
            for row_idx, row in enumerate(table):
                cells = [
                    (cell or "").replace("\n", " ").strip() for cell in row
                ]
                rows.append("| " + " | ".join(cells) + " |")
                if row_idx == 0:
                    rows.append("|" + "|".join(["---"] * len(cells)) + "|")
            if rows:
                rendered.append("\n".join(rows))
        return rendered

    def _parse_pdf_simple(
        self, content: bytes, warnings: list[str] | None = None
    ) -> tuple[list[ParsedBlock], list[str]]:
        """Simple PDF parser using pypdf (no OCR).

        Used as fallback when PDF processor is unavailable or for digital-only PDFs.
        """
        warnings = warnings or []
        reader = PdfReader(io.BytesIO(content))
        blocks: list[ParsedBlock] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append(
                    ParsedBlock.from_native_text(
                        text=text,
                        page=page_number,
                        block_index=len(blocks),
                    )
                )
        if blocks:
            return blocks, warnings

        if self.docling_enabled and self.parser_backend in {"auto", "docling"}:
            docling_blocks = self._parse_with_docling(".pdf", content)
            if docling_blocks:
                warnings.append(
                    "PDF không có lớp text; đã dùng Docling/OCR. Data owner cần kiểm duyệt."
                )
                return docling_blocks, warnings

        raise ParseError("Không trích xuất được văn bản từ PDF; cần OCR hoặc kiểm tra tệp.")

    def _parse_docx(self, content: bytes) -> tuple[list[ParsedBlock], list[str]]:
        document = Document(io.BytesIO(content))
        blocks: list[ParsedBlock] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if text:
                blocks.append(
                    ParsedBlock.from_native_text(
                        text=text,
                        page=None,
                        block_index=len(blocks),
                    ).model_copy(update={"source": "docx"})
                )
        for table in document.tables:
            table_markdown_rows = []
            for row_idx, row in enumerate(table.rows):
                values = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                row_str = "| " + " | ".join(values) + " |"
                table_markdown_rows.append(row_str)
                if row_idx == 0:
                    separators = ["---"] * len(values)
                    table_markdown_rows.append("| " + " | ".join(separators) + " |")
            if table_markdown_rows:
                blocks.append(
                    ParsedBlock.from_native_text(
                        text="\n".join(table_markdown_rows),
                        page=None,
                        block_index=len(blocks),
                    ).model_copy(update={"source": "docx"})
                )
        if not blocks:
            raise ParseError("DOCX không chứa văn bản có thể đọc.")
        return blocks, ["DOCX không cung cấp số trang ổn định; trích dẫn trang có thể để trống."]

    def _parse_text(self, content: bytes) -> tuple[list[ParsedBlock], list[str]]:
        text = ""
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1258"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not text.strip():
            raise ParseError("Không đọc được nội dung TXT.")
        paragraphs = [item.strip() for item in text.splitlines() if item.strip()]
        blocks = [
            ParsedBlock.from_native_text(
                text=item,
                page=None,
                block_index=index,
            ).model_copy(update={"source": "txt"})
            for index, item in enumerate(paragraphs)
        ]
        return blocks, ["TXT không có thông tin trang; trích dẫn trang sẽ để trống."]

    def _parse_with_docling(self, suffix: str, content: bytes) -> list[ParsedBlock]:
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            return []

        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)
            result = DocumentConverter().convert(str(temp_path))
            markdown = result.document.export_to_markdown().strip()
            return [
                ParsedBlock.from_native_text(
                    text=markdown,
                    page=None,
                    block_index=0,
                )
            ] if markdown else []
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
