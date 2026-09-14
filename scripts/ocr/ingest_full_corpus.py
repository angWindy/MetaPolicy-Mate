"""Re-ingest the OCR corpus through the canonical ingestion pipeline.

Thin wrapper around :mod:`scripts.ocr.reingest_via_canonical` so the
operator-facing CLI keeps the same ``--only`` / ``--skip-existing`` /
``--approved-by`` surface that earlier runs used. The actual parse +
sections + chunks logic now flows through
:class:`AiDocumentDigitizationService` — the same path the FastAPI
``POST /regulatory-documents/upload`` endpoint dispatches via
:class:`DigitizeDocumentCommand` — instead of the side-script that
wrote page-level sections.

Usage::

    # Idempotent re-ingest with full replace (recommended after an
    # OCR pipeline change so the production schema gets canonical
    # section types instead of the legacy ``page`` placeholder).
    python scripts/ocr/ingest_full_corpus.py --replace

    # Skip-Qdrant dry run — validates parser + section extraction
    # without calling OpenAI embeddings or Qdrant upsert.
    python scripts/ocr/ingest_full_corpus.py --skip-qdrant
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:  # pragma: no cover
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import create_engine, text as sa_text  # noqa: E402

# Re-use the per-file ingest + diacritic gate logic from the canonical
# re-ingest driver.
from scripts.ocr.reingest_via_canonical import (  # noqa: E402
    SCHOOLS,
    _ingest_one,
    _list_pdfs,
)

DEFAULT_CORPUS = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "ingest_full_corpus"


def _chunk_diacritic_ratio(conn, version_id: str) -> dict:
    """Diacritic ratio of all chunks for ``version_id``.

    Mirrors the gate used in ``data/ocr/outputs/ingest_full_corpus/
    summary.json`` so bench numbers stay comparable across runs.
    """
    rows = conn.execute(
        sa_text("SELECT text FROM public.document_chunks WHERE version_id = :v"),
        {"v": version_id},
    ).fetchall()
    if not rows:
        return {"chunk_count": 0, "diacritic_ratio": 0.0, "min_ratio": 0.0}
    diacritics = set(
        "ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    )
    ratios = []
    for (text,) in rows:
        if not text:
            continue
        d = sum(1 for c in text if c in diacritics)
        ratios.append(d / max(1, len(text)))
    return {
        "chunk_count": len(rows),
        "diacritic_ratio": round(sum(ratios) / max(1, len(ratios)), 4),
        "min_ratio": round(min(ratios), 4) if ratios else 0.0,
    }


async def _run(args: argparse.Namespace) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    pairs = _list_pdfs(args.corpus, set(args.only) if args.only else None, [])
    if not pairs:
        print("ERROR: no PDFs found in corpus", file=sys.stderr)
        return 1

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    args.out.mkdir(parents=True, exist_ok=True)

    # Optional --skip-existing pre-load: read titles already in the DB
    # so we can short-circuit duplicates. When --replace is on we skip
    # the short-circuit because the existing rows will be deleted
    # anyway.
    existing_titles: set[str] = set()
    if args.skip_existing and not args.replace:
        with engine.connect() as conn:
            rows = conn.execute(
                sa_text("SELECT title FROM public.documents")
            ).fetchall()
        existing_titles = {row[0] for row in rows if row[0]}
        print(f"Pre-loaded {len(existing_titles)} existing titles")

    summary: list[dict] = []
    for school, pdf in pairs:
        title_for_check = pdf.stem[:200]
        if args.skip_existing and title_for_check in existing_titles and not args.replace:
            print(f"SKIP {pdf.name}: already ingested")
            summary.append({"school": school, "pdf": pdf.name, "skipped": True})
            continue

        print(f"--- {school}/{pdf.name} ---")
        try:
            entry = await _ingest_one(
                engine=engine,
                pdf_path=pdf,
                school=school,
                ocr_engine=args.ocr_engine,
                approved_by=args.approved_by,
                replace=args.replace,
                push_qdrant=not args.skip_qdrant,
            )
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            summary.append(
                {
                    "school": school,
                    "pdf": pdf.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        with engine.connect() as conn:
            ratio = _chunk_diacritic_ratio(conn, entry["version_id"])
        entry.update(ratio)
        summary.append(entry)
        print(
            f"  -> sections={entry.get('section_count', '?')} "
            f"chunks={entry.get('chunk_count', '?')} "
            f"diacritic_ratio={ratio['diacritic_ratio']} "
            f"min_ratio={ratio['min_ratio']}"
        )

    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    failed = [s for s in summary if "error" in s]
    skipped = [s for s in summary if s.get("skipped")]
    succeeded = [s for s in summary if "version_id" in s]
    print(
        f"\n=== INGEST COMPLETE ===\n"
        f"Total: {len(summary)} PDFs "
        f"({len(succeeded)} ingested, "
        f"{len(skipped)} skipped, "
        f"{len(failed)} failed)"
    )
    print(f"Summary: {summary_path}")
    return 0 if not failed else 1


def main() -> int:
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
        choices=[s.lower() for s in SCHOOLS],
        help="Restrict to specific school(s); repeatable.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete existing rows that share the same document_number "
            "before re-ingesting. Use to backfill the production schema "
            "after OCR pipeline changes."
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help=(
            "Skip PDFs whose title already exists in the documents "
            "table. Ignored when --replace is also set (replace deletes "
            "first, so there's nothing to skip)."
        ),
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Skip Qdrant upsert. Validates parser + sections + chunks "
             "without OpenAI / Qdrant creds.",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=("rapidocr_vi", "pp_structure"),
        default="rapidocr_vi",
        help="OCR backend passed to AiDocumentDigitizationService.",
    )
    parser.add_argument(
        "--approved-by",
        type=str,
        default="ocr-bench@local",
        help="Operator name recorded on the ingest job for traceability.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
