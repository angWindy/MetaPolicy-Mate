"""Fix dict.txt — append 45 missing Vietnamese diacritics.

The bundled PP-OCRv6_medium_rec dict has 18 708 chars but only 30
Vietnamese diacritics. This script appends the missing 45 tone marks
(U+1EA0-U+1EF9 Latin Extended Additional range) so the recognizer can
emit Vietnamese text with full diacritic preservation.

Idempotent: re-running is safe (dedupe + stable sort).

Usage:
    python3 scripts/ocr/fix_dict_txt.py [--dict PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICT = REPO_ROOT / "data" / "ocr" / "outputs" / "onnx_models" / "rec_vi" / "dict.txt"
RUNTIME_DICT = REPO_ROOT / "ocr_models" / "rec_vi" / "dict.txt"

# Unicode range U+1EA0..U+1EF9 covers Latin Extended Additional.
# Every Vietnamese-specific char with a diacritic falls in here.
VIETNAMESE_EXTENDED = [chr(cp) for cp in range(0x1EA0, 0x1EFA)]


def load_lines(path: Path) -> list[str]:
    """Read dict lines as a list (preserving order)."""
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_lines(path: Path, lines: list[str]) -> None:
    """Write lines with LF separator, trailing newline."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fix_dict(dict_path: Path, *, dry_run: bool = False) -> dict[str, int]:
    """Append missing Vietnamese chars to ``dict_path``.

    Returns a report dict with ``before``, ``after``, ``added``.
    """
    if not dict_path.exists():
        raise FileNotFoundError(f"dict.txt not found: {dict_path}")

    lines = load_lines(dict_path)
    before_count = len(lines)
    present = set(lines)

    added: list[str] = []
    for ch in VIETNAMESE_EXTENDED:
        if ch not in present:
            added.append(ch)
            lines.append(ch)

    if not dry_run and added:
        # Stable sort: keep existing order, append new chars sorted by codepoint.
        existing = [ln for ln in lines if ln not in added]
        new_sorted = sorted(added)
        merged = existing + new_sorted
        write_lines(dict_path, merged)
        after_count = len(merged)
    else:
        after_count = before_count

    return {
        "before": before_count,
        "after": after_count,
        "added": len(added),
        "missing_now": [ch for ch in VIETNAMESE_EXTENDED if ch not in set(lines)],
        "path": str(dict_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dict", type=Path, default=DEFAULT_DICT, help="Path to dict.txt (default: dev workspace)")
    parser.add_argument("--runtime", action="store_true", help="Also copy to runtime dir ocr_models/rec_vi/dict.txt")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args(argv)

    report = fix_dict(args.dict, dry_run=args.dry_run)
    print(f"Path:      {report['path']}")
    print(f"Before:    {report['before']} chars")
    print(f"Added:     {report['added']} chars")
    print(f"After:     {report['after']} chars")
    if report["missing_now"]:
        print(f"Still missing: {report['missing_now']}")

    if args.runtime and not args.dry_run and report["added"] > 0:
        RUNTIME_DICT.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_DICT.write_text(args.dict.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Copied to:  {RUNTIME_DICT}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
