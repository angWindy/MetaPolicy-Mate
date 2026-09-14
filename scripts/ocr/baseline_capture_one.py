#!/usr/bin/env python3
"""Capture baseline chunks for the OCR migration plan (per-file, fast).

Phase H1.2 of PLAN.md §12. Same logic as ``baseline_capture.py`` but
runs each file in its own process so a timeout on a large hybrid PDF
doesn't lose the small (digital) baseline too.

Outputs:
    data/ocr/baseline/paddleocr_2517_chunks.json
    data/ocr/baseline/paddleocr_huce_1348_chunks.json (optional, may OOM)

Usage:
    python scripts/ocr/baseline_capture_one.py <pdf_path> <output_json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ingestion.pdf_processor.pipeline import (  # noqa: E402
    PDFProcessingPipeline,
    PipelineConfig,
)


def _chunks_to_dict(doc) -> dict:
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


def capture(pdf_path: Path, output: Path) -> bool:
    if not pdf_path.exists():
        print(f"SKIP: {pdf_path} not found", flush=True)
        return False

    print(f"Processing {pdf_path} ...", flush=True)
    pdf_bytes = pdf_path.read_bytes()
    # Cover DPI 600 (default), body DPI 300 — see
    # ``PDFProcessingPipeline._resolve_page_dpi``. Acceptable for a
    # baseline; a future phase can lower body DPI for the migration
    # bench without breaking this comparison.
    pipeline = PDFProcessingPipeline(PipelineConfig())
    try:
        doc = pipeline.process_pdf(
            pdf_bytes=pdf_bytes,
            document_id=pdf_path.stem,
            filename=pdf_path.name,
        )
    finally:
        pipeline.ocr_engine.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _chunks_to_dict(doc)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))

    total_chars = sum(len(p.get("native_text", "")) for p in payload["pages"])
    total_ocr_chars = sum(len(p.get("ocr_raw_text", "")) for p in payload["pages"])
    print(
        f"  -> {output}: pages={payload['total_pages']} "
        f"digital={payload['digital_pages']} hybrid={payload['hybrid_pages']} "
        f"native_chars={total_chars} ocr_chars={total_ocr_chars}",
        flush=True,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture baseline chunks for one PDF.")
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("output_json", type=Path)
    args = parser.parse_args()
    capture(args.pdf_path, args.output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
