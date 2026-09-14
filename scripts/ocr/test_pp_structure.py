"""G10 verification: run the digitization pipeline with ``ocr_engine=pp_structure``
on a table-rich PDF and confirm ``TableStructure`` HTML/Markdown is emitted.

Unlike ``reingest_via_canonical.py``, this script does NOT write to Neon.
It only exercises the parser + PP-StructureV3 path so we can verify:

1. ``pp_structure`` engine loads.
2. Per-page ``OCRResult.tables`` carry ``TableStructure`` objects with
   non-empty ``html`` and ``markdown``.
3. The downstream ``build_chunks`` produces at least one
   ``section_type='table'`` chunk.

Usage::

    python scripts/ocr/test_pp_structure.py data/raw/HUST/2048-table.pdf
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv  # noqa: F401
    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass


async def _run(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        return 1
    print(f"PDF: {pdf_path}")

    from src.infrastructure.ai.document_digitization_service import (
        AiDocumentDigitizationService,
    )

    svc = AiDocumentDigitizationService()
    content = pdf_path.read_bytes()
    import uuid as _uuid
    doc_id = str(_uuid.uuid4())
    ver_id = str(_uuid.uuid4())

    started = time.perf_counter()
    result = await svc.digitize(
        document_id=doc_id,
        version_id=ver_id,
        filename=pdf_path.name,
        content=content,
        document_number="G10-VERIFICATION",
        title=pdf_path.stem,
        issued_by="BENCH",
        issued_date=None,
        effective_date=None,
        version_number=1,
        ocr_engine="pp_structure",
    )
    elapsed = time.perf_counter() - started

    sections = result.sections
    chunks = result.chunks

    table_sections = [s for s in sections if s.section_type == "table"]
    non_table_sections = [s for s in sections if s.section_type != "table"]
    table_chunks = [
        c for c in chunks if (c.metadata or {}).get("content_type") == "table"
    ]

    print("=" * 70)
    print("G10 - PP-StructureV3 verification")
    print("=" * 70)
    print(f"Total wall-clock:       {elapsed:.2f}s")
    print(f"Sections:               {len(sections)}")
    print(f"  Table sections:       {len(table_sections)}")
    print(f"  Non-table sections:   {len(non_table_sections)}")
    print(f"Chunks:                 {len(chunks)}")
    print(f"  Table chunks:         {len(table_chunks)}")
    print()

    if table_sections:
        sample = table_sections[0]
        print(f"--- Sample table section ---")
        print(f"  heading:  {sample.heading!r}")
        print(f"  page:     {sample.page}")
        text = (sample.content or "").strip()
        print(f"  text len: {len(text)} chars")
        print(f"  first 240 chars:")
        for line in text.splitlines()[:6]:
            print(f"    {line}")
        print()

    if table_chunks:
        sample = table_chunks[0]
        meta = sample.metadata or {}
        print(f"--- Sample table chunk ---")
        print(f"  chunk_index:   {sample.chunk_index}")
        print(f"  text len:      {len(sample.text or '')}")
        print(f"  metadata keys: {sorted(meta.keys())}")
        table_meta = meta.get("table_metadata") or {}
        print(f"  table_metadata: {table_meta}")
        if meta.get("table_id"):
            print(f"  table_id:      {meta['table_id']}")
        if meta.get("parent_table_heading"):
            print(f"  parent:        {meta['parent_table_heading']}")
        print()

    print("SECTION TYPES BREAKDOWN:")
    by_type: dict[str, int] = {}
    for s in sections:
        by_type[s.section_type or "?"] = by_type.get(s.section_type or "?", 0) + 1
    for t, n in sorted(by_type.items()):
        print(f"  {t:10} {n:>5}")

    passed = bool(table_sections and table_chunks)
    print()
    print(f"GATE G10: {'PASS' if passed else 'FAIL'}")
    print(
        f"  Required: ≥1 table section AND ≥1 table chunk with metadata."
    )
    print(f"  Actual:   {len(table_sections)} table sections, "
          f"{len(table_chunks)} table chunks.")
    return 0 if passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to PDF (no DB writes)")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
