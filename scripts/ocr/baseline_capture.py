#!/usr/bin/env python3
"""Capture baseline chunks for the OCR migration plan.

Phase H1.2 of PLAN.md §12: dump processed-document chunks before any
backend swap so the post-refactor (Phase H1.2) and post-RapidOCR
(Phase H2) results can be diffed against a stable reference.

Outputs:
    data/ocr/baseline/paddleocr_2517_chunks.json
    data/ocr/baseline/paddleocr_huce_1348_chunks.json (one hybrid file)

Usage:
    python scripts/ocr/baseline_capture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Make src.* importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.pdf_processor.pipeline import (  # noqa: E402
    PDFProcessingPipeline,
    PipelineConfig,
)


HYBRID_FILE = "data/raw/HUCE/1348_ QĐ biên soạn, lựa chọn tài liệu giảng dạy final.pdf"
DIGITAL_FILE = "data/ocr/2517_QD_BGDDT.pdf"

OUT_DIR = Path("data/ocr/baseline")


def _chunks_to_dict(doc) -> dict:
    """Serialise a ProcessedDocument into a JSON-friendly dict."""
    return {
        "document_id": doc.document_id,
        "filename": doc.filename,
        "sha256": doc.sha256,
        "total_pages": doc.total_pages,
        "scan_pages": doc.scan_pages,
        "digital_pages": doc.digital_pages,
        "hybrid_pages": doc.hybrid_pages,
        "pages": [
            {
                "page_number": page.page_number,
                "page_type": page.page_type.value,
                "native_text": page.native_text,
                "ocr_blocks": (
                    [
                        {
                            "block_type": b.block_type.value,
                            "text": b.text,
                            "bbox": (
                                b.bbox.to_list() if b.bbox is not None else None
                            ),
                            "confidence": b.confidence,
                            "reading_order": b.reading_order,
                        }
                        for b in (page.ocr_result.blocks if page.ocr_result else [])
                    ]
                ),
                "ocr_raw_text": (
                    page.ocr_result.raw_text if page.ocr_result else ""
                ),
                "ocr_avg_confidence": (
                    page.ocr_result.average_confidence if page.ocr_result else 0.0
                ),
            }
            for page in doc.pages
        ],
    }


def capture(pdf_path: str, output: Path) -> None:
    if not Path(pdf_path).exists():
        print(f"SKIP: {pdf_path} not found")
        return

    print(f"Processing {pdf_path} ...")
    pdf_bytes = Path(pdf_path).read_bytes()
    pipeline = PDFProcessingPipeline(PipelineConfig())
    try:
        doc = pipeline.process_pdf(
            pdf_bytes=pdf_bytes,
            document_id=Path(pdf_path).stem,
            filename=Path(pdf_path).name,
        )
    finally:
        pipeline.ocr_engine.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = _chunks_to_dict(doc)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    total_chars = sum(len(p.get("native_text", "")) for p in payload["pages"])
    total_ocr_chars = sum(len(p.get("ocr_raw_text", "")) for p in payload["pages"])
    print(
        f"  -> {output}: pages={payload['total_pages']} "
        f"digital={payload['digital_pages']} hybrid={payload['hybrid_pages']} "
        f"native_chars={total_chars} ocr_chars={total_ocr_chars}"
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    capture(
        DIGITAL_FILE,
        OUT_DIR / "paddleocr_2517_chunks.json",
    )
    capture(
        HYBRID_FILE,
        OUT_DIR / "paddleocr_huce_1348_chunks.json",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
