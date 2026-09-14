"""Hybrid A/B runner — text-extract-first, RapidOCR fallback.

Runs the new hybrid pipeline on PDFs that mix digital pages and a few
scanned pages. The hybrid gate in :class:`PDFProcessingPipeline` decides
per page whether to OCR; the script then dumps the resulting
``ProcessedDocument`` to JSON under ``data/ocr/outputs/bench_hybrid/``.

The output schema matches the ``text_only_baseline.py`` output so the
two can be diffed by ``diff_chunks.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make src/ importable when run as ``python scripts/ocr/hybrid_text_first.py``.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.pdf_processor.pipeline import (  # noqa: E402
    PDFProcessingPipeline,
    PipelineConfig,
)
from src.ingestion.pdf_processor.ocr_engine import OCRConfig  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_hybrid"


def run_hybrid(pdf_path: Path, hybrid_text_threshold: int = 50) -> dict:
    """Run the hybrid pipeline on a single PDF and serialise the result."""
    cfg = PipelineConfig(
        ocr_config=OCRConfig(
            models_dir=REPO_ROOT / "data" / "ocr" / "outputs" / "onnx_models",
        ),
        hybrid_text_threshold=hybrid_text_threshold,
    )
    pipeline = PDFProcessingPipeline(config=cfg)
    pdf_bytes = pdf_path.read_bytes()
    processed = pipeline.process_pdf(
        pdf_bytes,
        document_id=pdf_path.stem,
        filename=pdf_path.name,
        dpi=200,
    )

    pages = []
    for p in processed.pages:
        pages.append(
            {
                "page": p.page_number,
                "page_type": p.page_type.value,
                "native_text": (p.native_text or "").strip(),
                "ocr_text": (p.ocr_result.raw_text if p.ocr_result else "").strip(),
                "char_count": len((p.ocr_result.raw_text if p.ocr_result else "").strip()),
                "block_count": len(p.ocr_result.blocks) if p.ocr_result else 0,
                "avg_confidence": (
                    p.ocr_result.average_confidence if p.ocr_result else 0.0
                ),
            }
        )

    return {
        "pdf": str(pdf_path),
        "engine": "hybrid_rapidocr_vi",
        "hybrid_text_threshold": hybrid_text_threshold,
        "page_count": len(pages),
        "digital_pages": processed.digital_pages,
        "scan_pages": processed.scan_pages,
        "pages": pages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        action="append",
        type=Path,
        required=True,
        help="PDF path(s) to process (repeatable).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        help="Hybrid text threshold (default: 50 chars).",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)

    summary = []
    for pdf_path in args.pdf:
        if not pdf_path.exists():
            print(f"SKIP {pdf_path} (not found)", file=sys.stderr)
            continue
        result = run_hybrid(pdf_path, args.threshold)
        out_path = args.out / f"{pdf_path.stem}_hybrid.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        summary.append(
            {
                "pdf": pdf_path.name,
                "pages": result["page_count"],
                "digital_pages": result["digital_pages"],
                "scan_pages": result["scan_pages"],
            }
        )
        print(
            f"OK {pdf_path.name}: {result['page_count']} pages, "
            f"digital={result['digital_pages']}, scan={result['scan_pages']}"
        )

    summary_path = args.out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
