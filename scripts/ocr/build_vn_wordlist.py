"""Build Vietnamese wordlist from DIGITAL pages in the corpus.

Scans all PDFs in ``data/raw/``, extracts text via PyMuPDF, splits into
tokens (Vietnamese-aware), collects frequency counts, and writes a JSON
file ``data/ocr/outputs/vn_wordlist.json``.

The wordlist is used by :mod:`src.ingestion.pdf_processor.vn_diacritic_restore`
to map diacritic-stripped OCR tokens back to their Vietnamese forms.
Data-driven — no hallucination risk because every word is grounded in
the actual corpus.

Usage::

    python3 scripts/ocr/build_vn_wordlist.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "vn_wordlist.json"

# Vietnamese-aware word tokeniser. Includes all letters used in legal
# docs (Đ, ă â ê ô ơ ư + tone marks + digits + ASCII).
_VN_WORD_RE = re.compile(
    r"[0-9A-Za-zÀÁÂĂĐÈÉÊÌÍÒÓÔƠƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỶỸỴ"
    r"àáâăđèéêìíòóôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ]+",
    re.UNICODE,
)

import unicodedata


def strip_diacritics(word: str) -> str:
    """Return a diacritic-stripped form for lookup via NFD decomposition."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def is_short_noise(token: str) -> bool:
    """Drop 1-letter noise tokens (a, I, etc.) and pure digits."""
    if not token:
        return True
    if len(token) < 2:
        return True
    if token.isdigit():
        return True
    return False


def extract_tokens_from_pdf(pdf_path: Path) -> Counter[str]:
    """Extract Vietnamese tokens from all pages of ``pdf_path``."""
    counter: Counter[str] = Counter()
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        print(f"  WARN: cannot open {pdf_path.name}: {exc}", file=sys.stderr)
        return counter
    for page in doc:
        try:
            text = page.get_text("text") or ""
        except Exception as exc:
            print(f"  WARN: get_text failed on page: {exc}", file=sys.stderr)
            continue
        for token in _VN_WORD_RE.findall(text):
            if is_short_noise(token):
                continue
            counter[token] += 1
    doc.close()
    return counter


def build_wordlist(pdf_paths: list[Path], min_freq: int = 2) -> dict[str, int]:
    """Build a word→frequency dict from all PDFs.

    Words seen fewer than ``min_freq`` times are dropped to keep the
    lookup dict compact and avoid typos from one-off OCR errors in
    born-digital PDFs (rare but possible).
    """
    master: Counter[str] = Counter()
    for pdf in pdf_paths:
        print(f"  extracting: {pdf.name}", file=sys.stderr)
        tokens = extract_tokens_from_pdf(pdf)
        master.update(tokens)
    filtered = {w: c for w, c in master.items() if c >= min_freq}
    return filtered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=REPO_ROOT / "data" / "raw",
                        help="Directory recursively scanned for *.pdf")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSON path")
    parser.add_argument("--min-freq", type=int, default=2, help="Min frequency to keep a word")
    args = parser.parse_args(argv)

    pdfs = sorted(args.data_dir.rglob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found under {args.data_dir}", file=sys.stderr)
        return 1
    print(f"Scanning {len(pdfs)} PDFs under {args.data_dir}...")
    wordlist = build_wordlist(pdfs, min_freq=args.min_freq)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(wordlist, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Written {len(wordlist)} unique Vietnamese tokens to {args.out}")
    print(f"Total token occurrences: {sum(wordlist.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
