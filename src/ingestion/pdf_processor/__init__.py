"""PDF Regulation Processing Pipeline for RAG ingestion.

Components:
- ImagePreprocessor: DPI 600, Binary Threshold preprocessing for OCR
- OCREngine: RapidOCR + PP-OCRv6 Vietnamese ONNX (CPU-friendly)
- PPStructureEngine: optional PP-StructureV3 wrapper for layout + tables
- PageClassifier: Digital / Scan / Hybrid classification
- TableExtractor: Heuristic grid detection + per-cell OCR
- DocumentNormalizer: Unified document model + suspicious OCR detection
- RuleBasedValidator: Legal document validation (Điều/Khoản/date)
- PDFProcessingPipeline: Orchestrates all components
"""

from __future__ import annotations

from src.ingestion.pdf_processor.document_normalizer import (
    DocumentNormalizer,
    NormalizerConfig,
    RuleBasedValidator,
    check_suspicious_content,
    normalize_text,
    update_legal_structure,
)
from src.ingestion.pdf_processor.image_preprocessor import (
    ImagePreprocessor,
    PreprocessConfig,
    PreprocessMode,
)
from src.ingestion.pdf_processor.ocr_engine import OCRConfig, OCREngine
from src.ingestion.pdf_processor.page_classifier import PageClassifier, PageType
from src.ingestion.pdf_processor.pipeline import PDFProcessingPipeline, PipelineConfig
from src.ingestion.pdf_processor.pp_structure import (
    PPStructureConfig,
    PPStructureEngine,
)
from src.ingestion.pdf_processor.schemas import (
    BlockType,
    BoundingBox,
    LegalStructure,
    NormalizedBlock,
    OCRBlock,
    OCRConfidence,
    OCRResult,
    OCRWord,
    ProcessedDocument,
    ProcessedPage,
    TableCell,
    TableStructure,
    VLMReviewRequest,
    VLMReviewResult,
)
from src.ingestion.pdf_processor.table_extractor import TableConfig, TableExtractor

__all__ = [
    # Preprocessing
    "ImagePreprocessor",
    "PreprocessConfig",
    "PreprocessMode",
    # OCR
    "OCREngine",
    "OCRConfig",
    "OCRResult",
    "OCRBlock",
    "OCRWord",
    "OCRConfidence",
    # PP-StructureV3 (optional layout + table pipeline)
    "PPStructureEngine",
    "PPStructureConfig",
    # Classification
    "PageClassifier",
    "PageType",
    # Tables
    "TableExtractor",
    "TableConfig",
    "TableStructure",
    "TableCell",
    # Normalization & Validation
    "DocumentNormalizer",
    "NormalizerConfig",
    "RuleBasedValidator",
    "normalize_text",
    "update_legal_structure",
    "check_suspicious_content",
    # Schemas
    "BlockType",
    "BoundingBox",
    "LegalStructure",
    "NormalizedBlock",
    "ProcessedDocument",
    "ProcessedPage",
    "VLMReviewRequest",
    "VLMReviewResult",
    # Pipeline
    "PDFProcessingPipeline",
    "PipelineConfig",
]
