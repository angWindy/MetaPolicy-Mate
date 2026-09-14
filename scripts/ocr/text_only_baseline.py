"""Pure text-extraction baseline for hybrid A/B bench.

Reads a PDF with PyMuPDF only — no OCR, no RapidOCR engine import.
Used as the cheap baseline in the text-only vs hybrid comparison on
the 4 MIXED files in ``data/raw/``.

Output schema matches the hybrid pipeline: a list of
``{page, page_type, native_text, blocks}`` records written to a JSON
file under ``data/ocr/outputs/bench_text_only/``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "bench_text_only"


def extract_text_only(pdf_path: Path) -> dict:
    """Extract text per page using ``pymupdf.Page.get_text`` only."""
    doc = pymupdf.open(pdf_path)
    pages = []
    for pno in range(len(doc)):
        page = doc[pno]
        text = page.get_text("text") or ""
        words = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span.get("bbox")
                    if not bbox:
                        continue
                    words.append(
                        {
                            "text": span.get("text", ""),
                            "bbox": list(bbox),
                            "confidence": 1.0,
                        }
                    )
        pages.append(
            {
                "page": pno + 1,
                "page_type": "DIGITAL",
                "native_text": text.strip(),
                "char_count": len(text.strip()),
                "block_count": len(words),
                "blocks": words,
            }
        )
    doc.close()
    return {
        "pdf": str(pdf_path),
        "engine": "text_only_pymupdf",
        "page_count": len(pages),
        "pages": pages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        action="append",
        type=Path,
        required=True,
        help="PDF path(s) to extract text from (repeatable).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT}).",
    )
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)

    summary = []
    for pdf_path in args.pdf:
        if not pdf_path.exists():
            print(f"SKIP {pdf_path} (not found)", file=sys.stderr)
            continue
        result = extract_text_only(pdf_path)
        out_path = args.out / f"{pdf_path.stem}_text.json"
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        total_chars = sum(p["char_count"] for p in result["pages"])
        empty_pages = [p["page"] for p in result["pages"] if p["char_count"] < 50]
        summary.append(
            {
                "pdf": pdf_path.name,
                "pages": result["page_count"],
                "total_chars": total_chars,
                "empty_or_short_pages": empty_pages,
            }
        )
        print(
            f"OK {pdf_path.name}: {result['page_count']} pages, "
            f"{total_chars} chars, {len(empty_pages)} empty/short pages"
        )

    summary_path = args.out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
