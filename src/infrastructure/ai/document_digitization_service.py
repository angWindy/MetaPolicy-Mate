from typing import Literal

from src.domain.schemas import (
    AccessScope,
    DocumentMetadata,
)
from src.ingestion.chunker import (
    build_chunks,
)
from src.ingestion.legal_structure import (
    extract_sections,
)
from src.ingestion.parser import (
    DocumentParser,
)
from src.rag.config import (
    get_rag_settings,
)

from src.application.common.interfaces.document_digitization_service import (
    DigitizationResult,
    DigitizedChunk,
    DigitizedSection,
    DocumentDigitizationService,
)


class AiDocumentDigitizationService(
    DocumentDigitizationService
):
    def __init__(
        self,
    ) -> None:
        settings = get_rag_settings()

        self._settings = settings

        self._parser = DocumentParser(
            parser_backend=(
                settings.parser_backend
            ),

            docling_enabled=(
                settings.docling_enabled
            ),

            ocr_enabled=(
                settings.ocr_enabled
            ),

            min_ocr_confidence=(
                settings.ocr_min_confidence
            ),

            ocr_languages=(
                settings.ocr_languages_list
            ),

            ocr_gpu=(
                settings.ocr_gpu
            ),

            ocr_batch_size=(
                settings.ocr_batch_size
            ),

            ocr_workers=(
                settings.ocr_workers
            ),

            ocr_low_confidence_threshold=(
                settings
                .ocr_low_confidence_threshold
            ),

            ocr_hybrid_text_threshold=(
                settings
                .ocr_hybrid_text_threshold
            ),

            preprocess_mode=(
                settings.preprocess_mode
            ),

            preprocess_dpi=(
                settings.preprocess_dpi
            ),

            preprocess_binary_threshold=(
                settings
                .preprocess_binary_threshold
            ),

            preprocess_denoise=(
                settings.preprocess_denoise
            ),

            preprocess_sharpen=(
                settings.preprocess_sharpen
            ),

            detect_tables=(
                settings.detect_tables
            ),

            vlm_enabled=(
                settings.vlm_enabled
            ),

            vlm_review_threshold=(
                settings.vlm_review_threshold
            ),

            ocr_engine_type=(
                settings.ocr_engine
            ),

            use_pp_structure=(
                settings.use_pp_structure
            ),

            pp_structure_text_det_limit_side_len=(
                settings
                .pp_structure_text_det_limit_side_len
            ),

            pp_structure_layout_threshold=(
                settings
                .pp_structure_layout_threshold
            ),
        )

    async def digitize(
        self,
        *,
        document_id: str,
        version_id: str,

        filename: str,
        content: bytes,

        document_number: str,
        title: str,
        issued_by: str,

        issued_date,
        effective_date,

        version_number: int,

        ocr_engine: Literal["rapidocr_vi", "pp_structure"] = "rapidocr_vi",
    ) -> DigitizationResult:
        # Derive use_pp_structure from ocr_engine choice. This is the only
        # runtime behavioural difference: pp_structure enables the layout-aware
        # pipeline (slower, better for wireless tables); rapidocr_vi uses the
        # hybrid RapidOCR + PP-OCRv6 path (faster, Vietnamese diacritic-safe).
        use_pp_structure = ocr_engine == "pp_structure"
        blocks, parser_warnings = (
            self._parser.parse(
                filename,
                content,
                override_use_pp_structure=use_pp_structure,
            )
        )

        # ``ocr_mode=True`` enables the OCR-artifact cleaner plus
        # multi-line article-title support. Idempotent on born-digital
        # text — the cleaner is a no-op when no ``Ả`` artifacts are
        # present, and digital PDFs already pack the article title on
        # the same line as ``Điều N.``. The relaxed mode keeps the
        # section-extraction path identical for digital and scan PDFs
        # so both flows emit comparable metadata.
        sections = extract_sections(
            blocks,
            ocr_mode=True,
        )

        metadata = DocumentMetadata(
            title=title,

            document_number=(
                document_number
            ),

            issued_by=issued_by,

            # Chỉ để thỏa contract AI cũ.
            # KHÔNG phải source-of-truth
            # authorization.
            owner_department="SYSTEM",

            issued_date=issued_date,

            effective_from=(
                effective_date
            ),

            access_level=(
                AccessScope.PUBLIC
            ),

            allowed_departments=[],

            version_number=(
                version_number
            ),
        )

        chunks = build_chunks(
            document_id=document_id,

            version_id=version_id,

            metadata=metadata,

            sections=sections,

            max_chars=(
                self._settings
                .chunk_max_chars
            ),

            overlap_chars=(
                self._settings
                .chunk_overlap_chars
            ),
        )

        warnings = list(
            parser_warnings
        )

        if not any(
            section.section_type
            == "article"
            for section in sections
        ):
            warnings.append(
                "Không nhận diện được cấu trúc "
                "Điều/Khoản; Admin cần kiểm tra."
            )

        section_results = [
            DigitizedSection(
                section_type=(
                    section.section_type
                ),

                section_number=(
                    section.section_number
                ),

                heading=(
                    section.heading
                ),

                heading_path=list(
                    section.heading_path
                ),

                content=(
                    section.text
                ),

                page=(
                    section.page
                ),

                sort_order=index,
            )
            for index, section
            in enumerate(sections)
        ]

        chunk_results = []

        for chunk in chunks:
            metadata_json = dict(
                chunk.metadata
            )

            #
            # QUAN TRỌNG:
            # Access control KHÔNG lấy từ
            # metadata AI.
            #
            metadata_json.pop(
                "owner_department",
                None,
            )

            metadata_json.pop(
                "access_level",
                None,
            )

            metadata_json.pop(
                "allowed_departments",
                None,
            )

            chunk_results.append(
                DigitizedChunk(
                    id=chunk.id,

                    chunk_index=(
                        chunk.chunk_index
                    ),

                    text=chunk.text,

                    embedding_text=(
                        chunk.embedding_text
                    ),

                    section_index=(
                        metadata_json.get(
                            "source_section_index"
                        )
                    ),

                    metadata=(
                        metadata_json
                    ),
                )
            )

        return DigitizationResult(
            sections=section_results,
            chunks=chunk_results,
            warnings=warnings,
        )