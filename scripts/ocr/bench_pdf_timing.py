"""Measure per-page OCR timing on a single raw PDF.

Reads a PDF from data/raw/<SCHOOL>/, runs the canonical digitization
service, and reports:

* Pages classified digital vs scan
* Whether the hybrid text-extract gate fired (and which direction)
* Per-page wall-clock time (avg, min, max, total)
* Number of OCR calls actually invoked
* Total chunks emitted + low_confidence fraction

Optional env knobs:

* ``OCR_LOW_CONFIDENCE_THRESHOLD`` (default 0.7; lower to 0.5 to
  surface more scan pages as low_confidence)
* ``OCR_HYBRID_TEXT_THRESHOLD`` (default 50; lower to surface more
  pages to OCR or higher to skip more)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _patch_pipeline_logger(pdf_name: str, log_path: Path) -> dict:
    """Install a per-page timing capture on PDFProcessingPipeline.

    Returns a dict that will be populated with per-page timing info
    (one entry per ``_process_page`` call).
    """
    from src.ingestion.pdf_processor import pipeline as pipeline_mod
    from src.ingestion.pdf_processor.pipeline import PDFProcessingPipeline
    from src.ingestion.pdf_processor.schemas import PageType

    timings: dict[str, object] = {
        "pages": [],
        "digital_pages": 0,
        "scan_pages": 0,
        "hybrid_pages": 0,
        "ocr_pages": 0,
        "digital_skipped_ocr": 0,
        "ocr_times": [],
        "digital_times": [],
    }

    # Capture log lines so we can see the hybrid gate firing
    import logging

    captured_lines: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
            line = self.format(record)
            if "hybrid_gate_override" in line or "_process_page" in line:
                captured_lines.append(line)

    cap = _CaptureHandler()
    cap.setLevel(logging.INFO)
    cap.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    pipeline_mod.logger.addHandler(cap)

    orig_process_page = PDFProcessingPipeline._process_page

    def _timed_process_page(self, page, page_num, dpi):  # type: ignore[no-redef]
        started = time.perf_counter()
        # Inspect classifier + threshold BEFORE running so we can decide
        # if the call will likely fire OCR.
        page_type = self.page_classifier.classify_page(page)
        threshold = self.config.hybrid_text_threshold
        native_len = len((page.get_text("text") or "").strip()) if threshold is not None else None
        will_ocr = page_type in (PageType.SCAN, PageType.HYBRID)
        if page_type == PageType.DIGITAL and threshold is not None and native_len < threshold:
            will_ocr = True  # forced OCR by override

        result = orig_process_page(self, page, page_num, dpi)
        elapsed = time.perf_counter() - started

        # Capture OCR confidence if available
        avg_conf = None
        if result.ocr_result is not None:
            avg_conf = result.ocr_result.average_confidence

        timings["pages"].append({
            "page": page_num,
            "page_type": result.page_type.value,
            "native_chars": native_len,
            "will_ocr": will_ocr,
            "elapsed_s": round(elapsed, 3),
            "avg_ocr_confidence": avg_conf,
        })
        if result.page_type == PageType.DIGITAL:
            timings["digital_pages"] += 1
            timings["digital_times"].append(elapsed)
            if not will_ocr:
                timings["digital_skipped_ocr"] += 1
        elif result.page_type == PageType.SCAN:
            timings["scan_pages"] += 1
            timings["ocr_times"].append(elapsed)
            timings["ocr_pages"] += 1
        else:
            timings["hybrid_pages"] += 1
            timings["ocr_times"].append(elapsed)
            timings["ocr_pages"] += 1
        return result

    PDFProcessingPipeline._process_page = _timed_process_page  # type: ignore[assignment]
    timings["_captured_lines"] = captured_lines
    timings["_log_path"] = log_path
    return timings


async def _run(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        return 1

    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timings = _patch_pipeline_logger(pdf_path.name, log_path)

    print(f"PDF: {pdf_path}")
    print(f"OCR_LOW_CONFIDENCE_THRESHOLD={os.environ.get('OCR_LOW_CONFIDENCE_THRESHOLD', '0.7')}")
    print(f"OCR_HYBRID_TEXT_THRESHOLD={os.environ.get('OCR_HYBRID_TEXT_THRESHOLD', '50')}")
    print()

    started = time.perf_counter()
    from src.infrastructure.ai.document_digitization_service import (
        AiDocumentDigitizationService,
    )

    svc = AiDocumentDigitizationService()
    content = pdf_path.read_bytes()
    import uuid as _uuid
    doc_id = str(_uuid.uuid4())
    ver_id = str(_uuid.uuid4())
    result = await svc.digitize(
        document_id=doc_id,
        version_id=ver_id,
        filename=pdf_path.name,
        content=content,
        document_number="BENCH-TIMING",
        title=pdf_path.stem,
        issued_by="BENCH",
        issued_date=None,
        effective_date=None,
        version_number=1,
        ocr_engine="rapidocr_vi",
    )
    total_s = time.perf_counter() - started

    chunks = result.chunks
    chunks_with_lc = sum(1 for c in chunks if (c.metadata or {}).get("low_confidence"))
    avg_chunk_len = (
        statistics.mean(len(c.text or "") for c in chunks) if chunks else 0.0
    )

    print("=" * 70)
    print("PAGE BREAKDOWN")
    print("=" * 70)
    print(f"  Total pages:        {len(timings['pages'])}")
    print(f"  Digital pages:      {timings['digital_pages']}")
    print(f"  Scan pages:         {timings['scan_pages']}")
    print(f"  Hybrid pages:       {timings['hybrid_pages']}")
    print(f"  OCR calls invoked:  {timings['ocr_pages']}")
    print(f"  Digital skipped OCR: {timings['digital_skipped_ocr']}")
    print()
    if timings["ocr_times"]:
        print(
            f"  OCR per-page (s):  "
            f"avg={statistics.mean(timings['ocr_times']):.3f} "
            f"min={min(timings['ocr_times']):.3f} "
            f"max={max(timings['ocr_times']):.3f} "
            f"median={statistics.median(timings['ocr_times']):.3f}"
        )
        print(
            f"  OCR total:         "
            f"{sum(timings['ocr_times']):.2f}s "
            f"({sum(timings['ocr_times'])/total_s*100:.1f}% of wall)"
        )
    if timings["digital_times"]:
        print(
            f"  Digital per-page (s): "
            f"avg={statistics.mean(timings['digital_times']):.3f} "
            f"min={min(timings['digital_times']):.3f} "
            f"max={max(timings['digital_times']):.3f}"
        )
    print(f"  Total wall-clock:   {total_s:.2f}s")
    print()
    print(
        f"  Chunks emitted:     {len(chunks)} "
        f"(avg len {avg_chunk_len:.0f} chars, "
        f"{chunks_with_lc} low_confidence)"
    )

    print()
    print("PER-PAGE DETAIL:")
    for entry in timings["pages"]:
        marker = "OCR" if entry["will_ocr"] else "   "
        conf_str = f"conf={entry['avg_ocr_confidence']:.3f}" if entry["avg_ocr_confidence"] is not None else ""
        print(
            f"  p{entry['page']:3} {entry['page_type']:8} "
            f"native_chars={entry['native_chars'] or '-':>5} "
            f"{marker} {entry['elapsed_s']:.3f}s  {conf_str}"
        )

    captured = timings["_captured_lines"]
    if captured:
        print()
        print("HYBRID GATE OVERRIDES:")
        for line in captured:
            print(f"  {line.strip()}")

    summary = {
        "pdf": str(pdf_path),
        "env_low_conf_threshold": float(
            os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD", "0.7")
        ),
        "env_hybrid_text_threshold": int(
            os.environ.get("OCR_HYBRID_TEXT_THRESHOLD", "50")
        ),
        "total_pages": len(timings["pages"]),
        "ocr_calls_invoked": timings["ocr_pages"],
        "scan_pages": timings["scan_pages"],
        "digital_pages": timings["digital_pages"],
        "hybrid_pages": timings["hybrid_pages"],
        "ocr_total_s": round(sum(timings["ocr_times"]), 3),
        "ocr_per_page_avg_s": round(
            statistics.mean(timings["ocr_times"]), 3
        ) if timings["ocr_times"] else 0.0,
        "ocr_per_page_median_s": round(
            statistics.median(timings["ocr_times"]), 3
        ) if timings["ocr_times"] else 0.0,
        "ocr_per_page_min_s": round(min(timings["ocr_times"]), 3) if timings["ocr_times"] else 0.0,
        "ocr_per_page_max_s": round(max(timings["ocr_times"]), 3) if timings["ocr_times"] else 0.0,
        "wall_total_s": round(total_s, 3),
        "chunks_emitted": len(chunks),
        "chunks_low_confidence": chunks_with_lc,
        "low_confidence_ratio": (
            round(chunks_with_lc / len(chunks), 4) if chunks else 0.0
        ),
        "per_page": timings["pages"],
        "hybrid_gate_fired": bool(captured),
    }
    log_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary: {log_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to PDF (raw, no DB writes)")
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("/tmp/pdf_timing.json"),
        help="Where to write the JSON summary",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
