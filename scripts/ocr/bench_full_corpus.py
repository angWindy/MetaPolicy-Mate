"""Bench the hybrid text-extract + RapidOCR pipeline against the full corpus.

Runs :mod:`scripts.ocr.text_only_baseline` and :mod:`scripts.ocr.hybrid_text_first`
on every PDF under ``data/raw/HUCE/`` and ``data/raw/HUST/`` (22 files in
total — the current production corpus), then re-runs :mod:`scripts.ocr.diff_chunks`
to verify the Vietnamese diacritic gate.

Outputs:
* ``data/ocr/outputs/bench_full_corpus/text_only/<stem>_text.json``
* ``data/ocr/outputs/bench_full_corpus/hybrid/<stem>_hybrid.json``
* ``data/ocr/outputs/bench_full_corpus/diff/<stem>_diff.json``
* ``data/ocr/outputs/bench_full_corpus/summary.json`` — gate report
* ``data/ocr/outputs/bench_full_corpus/summary.md`` — human-readable report

Usage::

    python scripts/ocr/bench_full_corpus.py
    python scripts/ocr/bench_full_corpus.py --only huce/hust
    python scripts/ocr/bench_full_corpus.py --threshold 50 --dpi 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Re-use the existing bench scripts as libraries.
from scripts.ocr.diff_chunks import diff_pair  # noqa: E402
from scripts.ocr.hybrid_text_first import run_hybrid  # noqa: E402
from scripts.ocr.text_only_baseline import extract_text_only  # noqa: E402

DEFAULT_CORPUS = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_full_corpus"
SCHOOLS = ("huce", "hust")


def _list_pdfs(corpus_dir: Path, only: set[str] | None) -> list[Path]:
    pdfs: list[Path] = []
    for school in SCHOOLS:
        if only and school not in only:
            continue
        school_dir = corpus_dir / school.upper()
        if not school_dir.is_dir():
            print(f"WARN: {school_dir} missing; skipping", file=sys.stderr)
            continue
        for pdf in sorted(school_dir.glob("*.pdf")):
            pdfs.append(pdf)
    return pdfs


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _page_level_stats(hybrid_doc: dict) -> dict:
    """Tally scan vs digital page counts from the hybrid output."""
    pages = hybrid_doc.get("pages", [])
    scan = sum(1 for p in pages if p.get("page_type") in ("scan", "hybrid"))
    digital = sum(1 for p in pages if p.get("page_type") == "digital")
    return {
        "total": len(pages),
        "digital": digital,
        "scan": scan,
    }


def _overall_gate(summary: list[dict]) -> dict:
    """Compute aggregate gate statistics across the corpus."""
    total_pdfs = len(summary)
    total_scan_pages = sum(s["scanned_pages"] for s in summary)
    failed_pdfs = [s for s in summary if s["diacritic_failures"] > 0]
    total_failures = sum(s["diacritic_failures"] for s in summary)
    return {
        "total_pdfs": total_pdfs,
        "total_scan_pages": total_scan_pages,
        "failed_pdfs": len(failed_pdfs),
        "total_diacritic_failures": total_failures,
        "gate_status": "PASS" if total_failures == 0 else "FAIL",
    }


def _write_markdown_report(summary: list[dict], gate: dict, out: Path) -> None:
    lines = [
        "# Bench full corpus — Vietnamese diacritic gate",
        "",
        f"- Gate status: **{gate['gate_status']}**",
        f"- Total PDFs: `{gate['total_pdfs']}`",
        f"- Total scanned pages: `{gate['total_scan_pages']}`",
        f"- PDFs with diacritic failures: `{gate['failed_pdfs']}`",
        f"- Total diacritic failures: `{gate['total_diacritic_failures']}`",
        "",
        "## Per-PDF",
        "",
        "| School | PDF | Pages | Scanned | Diacritic failures |",
        "|---|---|---|---|---|",
    ]
    for row in summary:
        lines.append(
            f"| {row['school']} | `{row['pdf']}` | {row['total_pages']} "
            f"| {row['scanned_pages']} | {row['diacritic_failures']} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help=f"Corpus root (default: {DEFAULT_CORPUS}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT}).",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=SCHOOLS,
        help="Restrict to specific school(s); repeatable.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        help="Hybrid text threshold (default: 50 chars).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Render DPI for hybrid pipeline (default: 200).",
    )
    args = parser.parse_args(argv)

    pdfs = _list_pdfs(args.corpus, set(args.only) if args.only else None)
    if not pdfs:
        print("ERROR: no PDFs found in corpus", file=sys.stderr)
        return 1

    text_dir = args.out / "text_only"
    hybrid_dir = args.out / "hybrid"
    diff_dir = args.out / "diff"

    summary: list[dict] = []

    for pdf in pdfs:
        stem = pdf.stem
        school = pdf.parent.name.lower()
        print(f"--- {school.upper()}/{pdf.name} ---")

        # 1. Text-only baseline
        text_payload = extract_text_only(pdf)
        text_path = text_dir / f"{stem}_text.json"
        _write_json(text_path, text_payload)
        empty_pages = sum(1 for p in text_payload["pages"] if p["char_count"] < 50)
        print(f"  text_only: {text_payload['page_count']} pages, {empty_pages} short")

        # 2. Hybrid pipeline (text-extract first, OCR fallback)
        try:
            hybrid_payload = run_hybrid(pdf, hybrid_text_threshold=args.threshold)
        except Exception as exc:
            print(f"  HYBRID FAILED: {exc}", file=sys.stderr)
            summary.append(
                {
                    "school": school,
                    "pdf": pdf.name,
                    "stem": stem,
                    "total_pages": text_payload["page_count"],
                    "scanned_pages": 0,
                    "diacritic_failures": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        hybrid_path = hybrid_dir / f"{stem}_hybrid.json"
        _write_json(hybrid_path, hybrid_payload)
        stats = _page_level_stats(hybrid_payload)
        print(
            f"  hybrid   : {stats['total']} pages, "
            f"digital={stats['digital']}, scan={stats['scan']}"
        )

        # 3. Per-page diff with diacritic gate
        diff = diff_pair(text_path, hybrid_dir)
        diff_path = diff_dir / f"{stem}_diff.json"
        _write_json(diff_path, diff)
        fails = len(diff["diacritic_failures"])
        print(f"  diff     : {fails} diacritic gate failures")

        summary.append(
            {
                "school": school,
                "pdf": pdf.name,
                "stem": stem,
                "total_pages": stats["total"],
                "scanned_pages": stats["scan"],
                "diacritic_failures": fails,
            }
        )

    gate = _overall_gate(summary)
    summary_path = args.out / "summary.json"
    _write_json(summary_path, {"gate": gate, "rows": summary})
    md_path = args.out / "summary.md"
    _write_markdown_report(summary, gate, md_path)

    print(f"\n=== BENCH COMPLETE ===")
    print(json.dumps(gate, indent=2))
    print(f"Summary: {summary_path}")
    print(f"Markdown report: {md_path}")
    return 0 if gate["gate_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
