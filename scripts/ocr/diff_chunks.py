"""Chunk-level diff between text-only baseline and hybrid output.

For each PDF, compares the text-only baseline JSON
(``data/ocr/outputs/bench_text_only/<name>_text.json``) and the hybrid
JSON (``data/ocr/outputs/bench_hybrid/<name>_hybrid.json``) per page.

Reports:
* Empty / short pages in text-only (candidates where hybrid OCR
  should win).
* Char-count delta per page (hybrid ≥ text-only expected; data loss
  would show a negative delta).
* Diacritic ratio per scanned page (Vietnamese quality gate: ≥ 0.05).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEXT = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_text_only"
DEFAULT_HYBRID = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_hybrid"
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_diff"

VIETNAMESE_DIACRITICS = set(
    "ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)


def diacritic_ratio(text: str) -> float:
    """Return the fraction of chars that are Vietnamese diacritics."""
    if not text:
        return 0.0
    diacritic_count = sum(1 for c in text if c in VIETNAMESE_DIACRITICS)
    return diacritic_count / max(1, len(text))


def _load_pages(path: Path) -> dict[int, dict]:
    data = json.loads(path.read_text())
    return {p["page"]: p for p in data.get("pages", [])}


def _iter_text_files(text_dir: Path) -> Iterable[Path]:
    return sorted(text_dir.glob("*_text.json"))


def diff_pair(
    text_path: Path,
    hybrid_dir: Path,
    *,
    min_chars_for_gate: int = 100,
) -> dict:
    """Compute per-page diff between text-only baseline and hybrid output.

    Pages with fewer than ``min_chars_for_gate`` characters of OCR
    output are excluded from the diacritic gate — for pages with only
    a page number, signature, or stamp the gate is meaningless and
    always reports ``ratio == 0``.
    """
    stem = text_path.name.replace("_text.json", "")
    hybrid_path = hybrid_dir / f"{stem}_hybrid.json"
    text_pages = _load_pages(text_path)
    hybrid_pages = (
        _load_pages(hybrid_path) if hybrid_path.exists() else {}
    )

    rows = []
    diacritic_failures = []
    for page_num in sorted(text_pages.keys()):
        t = text_pages[page_num]
        h = hybrid_pages.get(page_num)
        text_chars = t.get("char_count", 0)
        ocr_chars = h.get("char_count", 0) if h else 0
        ocr_text = h.get("ocr_text", "") if h else ""
        ratio = diacritic_ratio(ocr_text)

        if (
            h is not None
            and h.get("page_type") in ("scan", "hybrid")
            and ocr_chars >= min_chars_for_gate
            and ratio < 0.05
        ):
            diacritic_failures.append({"page": page_num, "ratio": round(ratio, 4)})

        rows.append(
            {
                "page": page_num,
                "text_chars": text_chars,
                "hybrid_chars": ocr_chars,
                "delta": ocr_chars - text_chars,
                "hybrid_page_type": h.get("page_type") if h else None,
                "diacritic_ratio": round(ratio, 4) if h else None,
            }
        )

    return {
        "pdf_stem": stem,
        "text_only_pdf": str(text_path),
        "hybrid_pdf": str(hybrid_path) if hybrid_path.exists() else None,
        "rows": rows,
        "diacritic_failures": diacritic_failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text-dir",
        type=Path,
        default=DEFAULT_TEXT,
        help=f"Text-only JSON dir (default: {DEFAULT_TEXT}).",
    )
    parser.add_argument(
        "--hybrid-dir",
        type=Path,
        default=DEFAULT_HYBRID,
        help=f"Hybrid JSON dir (default: {DEFAULT_HYBRID}).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Diff output dir (default: {DEFAULT_OUT}).",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    summary = []
    for text_path in _iter_text_files(args.text_dir):
        diff = diff_pair(text_path, args.hybrid_dir)
        out_path = args.out / f"{diff['pdf_stem']}_diff.json"
        out_path.write_text(json.dumps(diff, indent=2, ensure_ascii=False))
        fails = len(diff["diacritic_failures"])
        total_pages = len(diff["rows"])
        scanned_pages = [r for r in diff["rows"] if r["hybrid_page_type"] in ("scan", "hybrid")]
        summary.append(
            {
                "pdf_stem": diff["pdf_stem"],
                "total_pages": total_pages,
                "scanned_pages": len(scanned_pages),
                "diacritic_failures": fails,
            }
        )
        print(
            f"{diff['pdf_stem']}: {total_pages} pages, "
            f"{len(scanned_pages)} scanned, "
            f"{fails} diacritic gate failures"
        )

    summary_path = args.out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nSummary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
