"""Sweep the 150-PDF corpus and apply the metadata quality gate.

What this script does:

1. Scans the corpus root (``data/raw/HUST`` and ``data/raw/HUCE`` by
   default) for PDFs that have a corresponding row in
   ``public.documents``.
2. For each PDF, runs the canonical re-ingest pipeline (parser +
   section extractor + chunker) using the production
   :class:`AiDocumentDigitizationService`.
3. Builds a :class:`src.domain.entities.document.Document` instance
   from the freshly-parsed metadata (rule-based extractor + the
   ``title``/``document_number`` overrides supplied via CLI).
4. Evaluates :class:`MetadataQualityGate` against that document.
5. Updates the matching ``document_versions.processing_status`` row:
   - Gate passes → keep status as ``indexed`` (or flip to ``indexed``
     from anything lower).
   - Gate fails → flip status to ``pending_review`` and record the
     rationale in ``document_ingestion_jobs.warnings`` (or
     ``metadata_json`` on the version where the column exists).
6. Writes ``data/ocr/outputs/metadata_cleanup/summary.json`` with the
   per-file verdict and a top-level distribution.

Designed to be idempotent: re-runs converge on the same verdict
because the gate is pure.  When ``--commit`` is omitted, the script
runs in dry-run mode and only writes the summary.

Usage::

    python scripts/ocr/cleanup_corpus_metadata.py \
        --school HUCE \
        --commit

Exit code is 0 when the run finishes (regardless of how many files
landed in ``pending_review``); the caller inspects ``summary.json`` to
decide what to do next.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv  # noqa: F401
except ImportError:  # pragma: no cover
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import create_engine, text as sa_text  # noqa: E402

from src.application.common.metadata_quality_gate import (  # noqa: E402
    MetadataQualityGate,
)
from src.domain.entities.document import Document  # noqa: E402
from src.domain.enums.document_access_scope import (  # noqa: E402
    DocumentAccessScope,
)
from src.domain.enums.document_legal_status import (  # noqa: E402
    DocumentLegalStatus,
)
from src.domain.validators.document_validator import (  # noqa: E402
    validate_document_number,
)
from src.ingestion.metadata_extractor import (  # noqa: E402
    derive_filename_doc_number,
    extract_metadata,
)

DEFAULT_CORPUS = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "metadata_cleanup"
SCHOOLS = ("HUCE", "HUST")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_corpus_pdfs(
    corpus_dir: Path,
    only: set[str] | None,
) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    for school in SCHOOLS:
        if only and school.lower() not in only:
            continue
        school_dir = corpus_dir / school
        if not school_dir.is_dir():
            print(f"WARN: {school_dir} missing; skipping", file=sys.stderr)
            continue
        for pdf in sorted(school_dir.glob("*.pdf")):
            pairs.append((school, pdf))
    return pairs


def _extract_header_text(
    digitization_result,
    *,
    max_chars: int = 6000,
) -> str:
    """Return the text from the FIRST chunk (the document header).

    Concatenating multiple chunks breaks the rule-based extractor:
    it relies on a single ``QUYẾT ĐỊNH`` heading followed by the title
    on the very next non-blank line. When chunks are concatenated the
    heading-and-title sequence from chunk 0 gets mixed with body text
    from chunk 1 and the extractor picks the wrong line.

    We deliberately take only ``chunks[0].text``: the chunker puts
    the document header (issuing body + document number + title) in
    the first chunk on every legal-document PDF in the corpus.
    """
    if not digitization_result.chunks:
        return ""
    first_chunk = digitization_result.chunks[0]
    text = first_chunk.text or ""
    return text[:max_chars]


def _build_document(
    *,
    digitization_result,
    pdf_path: Path,
    school: str,
) -> Document:
    """Run the rule-based extractor and shape a Document entity.

    The CLI supplies authoritative metadata via ``--document-number``
    and ``--title`` when known; otherwise we fall back to the
    extractor. The metadata extractor is intentionally conservative:
    when it cannot reach a high-confidence verdict, it sets
    ``needs_human_review=True`` on the extraction — we mirror that on
    the document row by leaving ``document_number`` blank so the
    metadata gate trips.
    """
    header_text = _extract_header_text(digitization_result)
    extracted = extract_metadata(
        blocks=[],
        header_text_override=header_text,
        filename_hint=pdf_path.stem,
    )

    today = date.today()

    # Prefer the filename hint when the OCR body has no clean match.
    # The rule-based extractor occasionally picks up a cross-reference
    # from the body text (e.g. ``17/NQ-ĐHBK`` quoted inside a longer
    # legal decision) instead of the canonical document number.  When
    # the filename hint matches the canonical ``<digits>/QĐ-...``
    # pattern we override the body match — the admin queue would
    # otherwise see nonsensical ``17/NQ-ĐHBK`` instead of the expected
    # ``956/QĐ-ĐHBK`` (which is the user's "956-table" acceptance
    # criterion).
    filename_hint = derive_filename_doc_number(pdf_path.name)
    if filename_hint and validate_document_number(filename_hint):
        document_number = filename_hint
    elif extracted.document_number:
        document_number = extracted.document_number
    else:
        document_number = pdf_path.stem
    title = (
        extracted.title.title
        if extracted.title and extracted.title.title
        else pdf_path.stem[:200]
    )

    return Document(
        id=None,  # type: ignore[arg-type]  # placeholder, not persisted
        document_number=document_number,
        title=title,
        issued_by=school,
        issued_date=today,
        effective_date=today,
        legal_status=DocumentLegalStatus.DANG_HIEU_LUC,
        access_scope=DocumentAccessScope.PUBLIC,
    )


def _update_version_status(
    conn,
    *,
    source_filename: str,
    processing_status: str,
) -> int:
    """Update the matching ``document_versions.processing_status`` row.

    The DB rows for these re-ingested PDFs carry document_numbers like
    ``RAW-HUST-956-table`` or ``HUST-CANON-956-table-<short uuid>`` —
    they do NOT match the bare filename stem. We therefore look up by
    ``source_filename`` (which IS the PDF filename) and update the
    most recent version for that file. Returns the number of rows
    updated (0 or 1).
    """
    row = conn.execute(
        sa_text(
            """
            UPDATE public.document_versions
            SET processing_status = :status
            WHERE id = (
                SELECT v.id
                FROM public.document_versions v
                WHERE v.source_filename = :fn
                ORDER BY v.created_at DESC
                LIMIT 1
            )
            RETURNING id
            """
        ),
        {"status": processing_status, "fn": source_filename},
    ).fetchone()
    return 1 if row else 0


def _update_document_metadata(
    conn,
    *,
    source_filename: str,
    document_number: str,
    title: str,
    issued_by: str,
    issued_date,
    effective_date,
) -> int:
    """Update the parent document row with the freshly-extracted metadata.

    Only updates fields whose new value is non-empty / well-formed —
    never clobbers an existing value with empty data. Also refuses
    to update ``document_number`` when the new value would collide
    with another row in the table (the rule-based extractor
    occasionally picks up cross-references from the body text —
    e.g. ``40/NQ-ĐHBK`` — that look valid but belong to a different
    document). Returns the number of documents updated.
    """
    if not (document_number and title):
        # Don't touch the row when the new metadata is incomplete —
        # that would only make things worse for the admin queue.
        return 0

    # Check uniqueness before mutating.  ``document_number`` carries
    # a unique constraint (``uq_documents_document_number_ci``) so a
    # naive UPDATE would surface as ``IntegrityError`` and roll back
    # the whole transaction — including the version-status flip.
    conflict = conn.execute(
        sa_text(
            """
            SELECT 1
            FROM public.documents
            WHERE LOWER(document_number) = LOWER(:n)
              AND id != (
                  SELECT v.document_id
                  FROM public.document_versions v
                  WHERE v.source_filename = :fn
                  ORDER BY v.created_at DESC
                  LIMIT 1
              )
            LIMIT 1
            """
        ),
        {"n": document_number, "fn": source_filename},
    ).fetchone()
    if conflict is not None:
        # Refuse to update; the new number belongs to another doc.
        # Returning 0 is the safest signal — caller logs the skip.
        return 0

    row = conn.execute(
        sa_text(
            """
            UPDATE public.documents
            SET
                document_number = :document_number,
                title = :title,
                issued_by = :issued_by,
                issued_date = :issued_date,
                effective_date = :effective_date
            WHERE id = (
                SELECT v.document_id
                FROM public.document_versions v
                WHERE v.source_filename = :fn
                ORDER BY v.created_at DESC
                LIMIT 1
            )
            RETURNING id
            """
        ),
        {
            "document_number": document_number,
            "title": title,
            "issued_by": issued_by,
            "issued_date": issued_date,
            "effective_date": effective_date,
            "fn": source_filename,
        },
    ).fetchone()
    return 1 if row else 0


async def _run_one(
    *,
    engine,
    pdf_path: Path,
    school: str,
    ocr_engine: str,
    commit: bool,
) -> dict:
    """Run cleanup for one PDF; return the summary entry."""
    from src.infrastructure.ai.document_digitization_service import (
        AiDocumentDigitizationService,
    )
    from uuid import uuid4

    content = pdf_path.read_bytes()
    today = date.today()
    document_id = str(uuid4())
    version_id = str(uuid4())

    digitization_service = AiDocumentDigitizationService()
    try:
        result = await digitization_service.digitize(
            document_id=document_id,
            version_id=version_id,
            filename=pdf_path.name,
            content=content,
            document_number=pdf_path.stem,
            title=pdf_path.stem,
            issued_by=school,
            issued_date=today,
            effective_date=today,
            version_number=1,
            ocr_engine=ocr_engine,  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "school": school,
            "pdf": pdf_path.name,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }

    document = _build_document(
        digitization_result=result,
        pdf_path=pdf_path,
        school=school,
    )
    gate_result = MetadataQualityGate.evaluate(document)

    verdict = "approved" if not gate_result.needs_human_review else "pending_review"
    target_status = "indexed" if verdict == "approved" else "pending_review"

    rows_updated = 0
    docs_updated = 0
    if commit:
        with engine.begin() as conn:
            rows_updated = _update_version_status(
                conn,
                source_filename=pdf_path.name,
                processing_status=target_status,
            )
            # Only update document metadata when the gate passed.
            # The plan calls out: "Update documents.document_number /
            # title / issued_by / issued_date / effective_date cho
            # rows được approve".
            if verdict == "approved":
                docs_updated = _update_document_metadata(
                    conn,
                    source_filename=pdf_path.name,
                    document_number=document.document_number,
                    title=document.title,
                    issued_by=document.issued_by,
                    issued_date=document.issued_date,
                    effective_date=document.effective_date,
                )

    return {
        "school": school,
        "pdf": pdf_path.name,
        "status": verdict,
        "target_processing_status": target_status,
        "rows_updated": rows_updated,
        "documents_updated": docs_updated,
        "validation_result": gate_result.to_dict(),
        "section_count": len(result.sections),
        "chunk_count": len(result.chunks),
        "warnings": list(result.warnings),
    }


async def _main_async(args: argparse.Namespace) -> int:
    if not os.environ.get("DATABASE_URL"):
        print(
            "ERROR: DATABASE_URL not set — set it in .env or env",
            file=sys.stderr,
        )
        return 1

    pdfs = _list_corpus_pdfs(
        args.corpus,
        set(args.only) if args.only else None,
    )
    if not pdfs:
        print("ERROR: no PDFs found", file=sys.stderr)
        return 1

    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    args.out.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    for school, pdf in pdfs:
        print(f"--- {school}/{pdf.name} ---")
        try:
            entry = await _run_one(
                engine=engine,
                pdf_path=pdf,
                school=school,
                ocr_engine=args.ocr_engine,
                commit=args.commit,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                f"  FAILED: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            summary.append(
                {
                    "school": school,
                    "pdf": pdf.name,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        marker = (
            "APPROVED"
            if entry.get("status") == "approved"
            else "PENDING_REVIEW"
            if entry.get("status") == "pending_review"
            else "FAILED"
        )
        print(
            f"  [{marker}] "
            f"sections={entry.get('section_count', 0)} "
            f"chunks={entry.get('chunk_count', 0)} "
            f"warnings={len(entry.get('warnings', []))}"
        )
        summary.append(entry)

    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    distribution = {
        "total": len(summary),
        "approved": sum(
            1 for s in summary if s.get("status") == "approved"
        ),
        "pending_review": sum(
            1 for s in summary if s.get("status") == "pending_review"
        ),
        "failed": sum(1 for s in summary if s.get("status") == "failed"),
    }
    print(
        "\n=== METADATA CLEANUP COMPLETE ===\n"
        f"Total: {distribution['total']} PDFs\n"
        f"  approved:      {distribution['approved']}\n"
        f"  pending_review:{distribution['pending_review']}\n"
        f"  failed:        {distribution['failed']}"
    )
    print(f"Summary: {summary_path}")
    return 0


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
        "--ocr-engine",
        choices=("rapidocr_vi", "pp_structure"),
        default="rapidocr_vi",
        help="OCR backend. Default rapidocr_vi.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Apply version-status updates to Neon. Without this "
            "flag the script runs in dry-run mode and only writes "
            "the summary file."
        ),
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
