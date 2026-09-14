"""Canonical re-ingest driver for the OCR corpus.

Replaces ``scripts/ocr/ingest_one_cloud.py`` (which bypassed
``extract_sections``/``build_chunks`` and the full Qdrant pipeline) by
routing every PDF through :class:`AiDocumentDigitizationService` —
the same parser / section extractor / chunker the FastAPI ingest
endpoint dispatches via :class:`DigitizeDocumentHandler`.

Per file the driver:

1. Runs :meth:`AiDocumentDigitizationService.digitize` — gets
   ``DigitizationResult.sections`` and ``DigitizationResult.chunks``
   with the canonical metadata contract (``section_type``,
   ``section_number``, ``heading_path``, ``previous_chunk_id``,
   ``next_chunk_id``, ``low_confidence``, ...).
2. Persists ``documents`` + ``document_versions`` + ``document_sections``
   + ``document_chunks`` rows to Neon (matches the production schema).
   Re-ingest is opt-in via ``--replace``: existing versions with the
   same ``document_number`` are deleted first so the new digitised
   version replaces the page-level sections / naive metadata left over
   from the side-script.
3. Optionally upserts Qdrant points with the canonical
   ``QdrantPayload`` shape (skippable via ``--skip-qdrant`` so bench
   runs without OpenAI / Qdrant secrets still validate the parser +
   section / chunk pipeline).

Usage::

    python scripts/ocr/reingest_via_canonical.py --replace
    python scripts/ocr/reingest_via_canonical.py --only huce --skip-qdrant
    python scripts/ocr/reingest_via_canonical.py --ocr-engine pp_structure \
        data/raw/HUCE/2048-table.pdf

Why we do not dispatch through ``DigitizeDocumentCommand`` directly:
the production handler requires a fully-wired FastAPI ``ServiceContainer``
(repos, rag_index_service, file_storage, ...). For an offline bench
script that builds rows from raw PDF bytes the simpler call chain above
is sufficient and keeps the script self-contained. The output schema
matches what the production handler would persist.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# dotenv is optional — the env may already be loaded by the shell.
try:
    from dotenv import load_dotenv  # noqa: F401
except ImportError:  # pragma: no cover
    load_dotenv = None
if load_dotenv is not None:
    load_dotenv(REPO_ROOT / ".env")

from sqlalchemy import create_engine, text as sa_text  # noqa: E402

from src.application.common.interfaces.document_digitization_service import (  # noqa: E402
    DigitizedChunk,
    DigitizedSection,
)
from src.infrastructure.ai.document_digitization_service import (  # noqa: E402
    AiDocumentDigitizationService,
)

DEFAULT_CORPUS = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "ocr" / "outputs" / "reingest_canonical"
SCHOOLS = ("HUCE", "HUST")


# ---------------------------------------------------------------------- #
# DB helpers
# ---------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _document_number(prefix: str, stem: str) -> str:
    """Stable ``document_number`` for a PDF.

    Format: ``<SCHOOL>-CANON-<stem>-<short uuid>`` so re-ingests are
    idempotent when ``--replace`` is passed (we delete by
    ``document_number`` before inserting).
    """
    short = uuid4().hex[:6]
    safe_stem = stem.replace("/", "-").replace(" ", "-")[:80]
    return f"{prefix}-CANON-{safe_stem}-{short}"


def _delete_existing_version_by_doc_number(
    conn, document_number: str
) -> int:
    """Hard-delete prior rows for ``document_number``.

    Returns the count of ``document_chunks`` rows removed so the caller
    can log the cleanup.
    """
    sql_docs = sa_text(
        "SELECT id FROM public.documents WHERE document_number = :n"
    )
    document_ids = [
        row[0]
        for row in conn.execute(sql_docs, {"n": document_number}).fetchall()
    ]
    if not document_ids:
        return 0

    chunk_count = 0
    for doc_id in document_ids:
        chunk_count += (
            conn.execute(
                sa_text(
                    "SELECT count(*) FROM public.document_chunks "
                    "WHERE version_id IN (SELECT id FROM public.document_versions "
                    "WHERE document_id = :d)"
                ),
                {"d": doc_id},
            ).scalar()
            or 0
        )
        conn.execute(
            sa_text(
                "DELETE FROM public.document_chunks WHERE version_id IN "
                "(SELECT id FROM public.document_versions WHERE document_id = :d)"
            ),
            {"d": doc_id},
        )
        conn.execute(
            sa_text(
                "DELETE FROM public.document_sections WHERE version_id IN "
                "(SELECT id FROM public.document_versions WHERE document_id = :d)"
            ),
            {"d": doc_id},
        )
        conn.execute(
            sa_text(
                "DELETE FROM public.document_ingestion_jobs WHERE version_id IN "
                "(SELECT id FROM public.document_versions WHERE document_id = :d)"
            ),
            {"d": doc_id},
        )
        conn.execute(
            sa_text(
                "DELETE FROM public.document_versions WHERE document_id = :d"
            ),
            {"d": doc_id},
        )
        conn.execute(
            sa_text("DELETE FROM public.documents WHERE id = :d"),
            {"d": doc_id},
        )
    return int(chunk_count)


def _insert_documents_row(
    conn,
    *,
    document_id: str,
    document_number: str,
    title: str,
    issued_by: str,
    today: date,
    now_iso: str,
    access_scope: str = "PUBLIC",
) -> None:
    conn.execute(
        sa_text(
            """
            INSERT INTO public.documents (
                id, document_number, title, issued_by,
                issued_date, effective_date, legal_status,
                created_at, updated_at, access_scope
            ) VALUES (
                :id, :document_number, :title, :issued_by,
                :issued_date, :effective_date, :legal_status,
                :created_at, :updated_at, :access_scope
            )
            """
        ),
        {
            "id": document_id,
            "document_number": document_number,
            "title": title[:500],
            "issued_by": issued_by[:255],
            "issued_date": today,
            "effective_date": today,
            "legal_status": "effective",
            "created_at": now_iso,
            "updated_at": now_iso,
            "access_scope": access_scope,
        },
    )


def _insert_version_row(
    conn,
    *,
    version_id: str,
    document_id: str,
    version_number: int,
    processing_status: str,
    checksum: str,
    source_filename: str,
    source_bytes: int,
    now_iso: str,
) -> None:
    conn.execute(
        sa_text(
            """
            INSERT INTO public.document_versions (
                id, document_id, version_number, processing_status,
                checksum, source_filename, object_key,
                content_type, size_bytes, created_at
            ) VALUES (
                :id, :document_id, :version_number, :processing_status,
                :checksum, :source_filename, :object_key,
                :content_type, :size_bytes, :created_at
            )
            """
        ),
        {
            "id": version_id,
            "document_id": document_id,
            "version_number": version_number,
            "processing_status": processing_status,
            "checksum": checksum,
            "source_filename": source_filename[:255],
            "object_key": f"ocr-bench/{source_filename}",
            "content_type": "application/pdf",
            "size_bytes": source_bytes,
            "created_at": now_iso,
        },
    )


def _insert_sections_rows(
    conn,
    sections: list[DigitizedSection],
    version_id: str,
) -> int:
    """Persist sections. Returns number of rows written."""
    written = 0
    for section in sections:
        # ``section.content`` carries ``max_chars * 4`` of body text —
        # column cap on ``document_sections.content`` is text in Postgres
        # so no truncation needed.
        conn.execute(
            sa_text(
                """
                INSERT INTO public.document_sections (
                    id, version_id, section_type, section_number,
                    heading, heading_path, content, page, sort_order
                ) VALUES (
                    :id, :version_id, :section_type, :section_number,
                    :heading, CAST(:heading_path AS JSONB),
                    :content, :page, :sort_order
                )
                """
            ),
            {
                "id": str(uuid4()),
                "version_id": version_id,
                "section_type": section.section_type or "preamble",
                "section_number": (
                    str(section.section_number)[:50]
                    if section.section_number is not None
                    else None
                ),
                "heading": (
                    section.heading[:1000] if section.heading else None
                ),
                "heading_path": json.dumps(
                    section.heading_path[:50]
                    if section.heading_path
                    else []
                ),
                "content": section.content,
                "page": section.page,
                "sort_order": section.sort_order,
            },
        )
        written += 1
    return written


def _insert_chunks_rows(
    conn,
    chunks: list[DigitizedChunk],
    sections: list[DigitizedSection],
    version_id: str,
) -> int:
    """Persist chunks. ``section_id`` resolves back to a section row.

    Caller is responsible for inserting sections FIRST so the FK lookup
    works. ``metadata_json`` is the canonical payload that the original
    ``build_chunks`` produces (article / clause / point aliases plus the
    full ``heading_path``). The downstream ``RagIndexService.index_chunks``
    reads the same payload to build the Qdrant point.
    """
    written = 0
    section_id_by_index = {
        idx: str(uuid4()) for idx in range(len(sections))
    }
    # We need section UUIDs that match what we just inserted. Re-query.
    section_rows = conn.execute(
        sa_text(
            "SELECT id, sort_order FROM public.document_sections "
            "WHERE version_id = :v ORDER BY sort_order"
        ),
        {"v": version_id},
    ).fetchall()
    if len(section_rows) == len(sections):
        for sec_row, idx in zip(section_rows, range(len(sections))):
            section_id_by_index[idx] = str(sec_row[0])

    for chunk in chunks:
        section_id = None
        if (
            chunk.section_index is not None
            and 0 <= chunk.section_index < len(section_id_by_index)
        ):
            section_id = section_id_by_index[chunk.section_index]

        text = chunk.text or ""
        if not text.strip():
            continue
        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        metadata_json = dict(chunk.metadata)
        # Strip keys the production handler drops (not persisted to PG
        # metadata_json because Qdrant owns them).
        metadata_json.pop("allowed_units", None)
        metadata_json.pop("access_scope", None)

        conn.execute(
            sa_text(
                """
                INSERT INTO public.document_chunks (
                    id, version_id, section_id, chunk_index,
                    text, embedding_text, content_hash, metadata_json
                ) VALUES (
                    :id, :version_id, :section_id, :chunk_index,
                    :text, :embedding_text, :content_hash,
                    CAST(:metadata_json AS JSONB)
                )
                """
            ),
            {
                "id": chunk.id,
                "version_id": version_id,
                "section_id": section_id,
                "chunk_index": chunk.chunk_index,
                "text": text,
                "embedding_text": chunk.embedding_text,
                "content_hash": content_hash,
                "metadata_json": json.dumps(metadata_json),
            },
        )
        written += 1
    return written


# ---------------------------------------------------------------------- #
# Per-PDF ingestion
# ---------------------------------------------------------------------- #


async def _ingest_one(
    *,
    engine,
    pdf_path: Path,
    school: str,
    ocr_engine: str,
    approved_by: str,
    replace: bool,
    push_qdrant: bool,
) -> dict:
    """Run the canonical pipeline for one PDF and persist rows to Neon.

    Returns a summary dict with ``document_id``, ``version_id``,
    ``chunk_count``, ``section_count``, plus warning strings.
    """
    content = pdf_path.read_bytes()
    today = date.today()
    now_iso = _now_iso()
    document_id = str(uuid4())
    version_id = str(uuid4())
    document_number = _document_number(school, pdf_path.stem)

    # 1. Run the canonical digitization service (parser + sections + chunks).
    digitization_service = AiDocumentDigitizationService()
    result = await digitization_service.digitize(
        document_id=document_id,
        version_id=version_id,
        filename=pdf_path.name,
        content=content,
        document_number=document_number,
        title=pdf_path.stem[:200],
        issued_by=school,
        issued_date=today,
        effective_date=today,
        version_number=1,
        ocr_engine=ocr_engine,  # type: ignore[arg-type]
    )

    # 2. Persist via raw SQL (Neon production schema).
    summary: dict = {
        "school": school,
        "pdf": pdf_path.name,
        "document_id": document_id,
        "version_id": version_id,
        "document_number": document_number,
        "ocr_engine": ocr_engine,
        "section_count": 0,
        "chunk_count": 0,
        "warnings": list(result.warnings),
        "replaced_old_chunks": 0,
    }

    with engine.begin() as conn:
        if replace:
            removed = _delete_existing_version_by_doc_number(
                conn, document_number
            )
            summary["replaced_old_chunks"] = removed

        _insert_documents_row(
            conn,
            document_id=document_id,
            document_number=document_number,
            title=pdf_path.stem[:200],
            issued_by=school,
            today=today,
            now_iso=now_iso,
        )
        _insert_version_row(
            conn,
            version_id=version_id,
            document_id=document_id,
            version_number=1,
            processing_status="indexed",
            checksum=_sha256_hex(content),
            source_filename=pdf_path.name,
            source_bytes=len(content),
            now_iso=now_iso,
        )
        summary["section_count"] = _insert_sections_rows(
            conn, result.sections, version_id
        )
        summary["chunk_count"] = _insert_chunks_rows(
            conn, result.chunks, result.sections, version_id
        )

    summary["approved_by"] = approved_by
    summary["completed_at"] = _now_iso()

    return summary


# ---------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------- #


def _list_pdfs(
    corpus_dir: Path, only: set[str] | None, extra: list[Path]
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
    for path in extra:
        # Infer school from parent folder, default to HUCE.
        school = path.parent.name if path.parent.name in SCHOOLS else "HUCE"
        pairs.append((school, path))
    return pairs


async def _main_async(args: argparse.Namespace) -> int:
    if not os.environ.get("DATABASE_URL"):
        print(
            "ERROR: DATABASE_URL not set — set it in .env or env",
            file=sys.stderr,
        )
        return 1

    pdfs = _list_pdfs(
        args.corpus,
        set(args.only) if args.only else None,
        args.pdf or [],
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
            print(
                f"  FAILED: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            summary.append(
                {
                    "school": school,
                    "pdf": pdf.name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        print(
            f"  sections={entry['section_count']} "
            f"chunks={entry['chunk_count']} "
            f"warnings={len(entry['warnings'])} "
            f"replaced_old_chunks={entry.get('replaced_old_chunks', 0)}"
        )
        summary.append(entry)

    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    failed = [s for s in summary if "error" in s]
    succeeded = [s for s in summary if "version_id" in s]
    print(
        f"\n=== REINGEST COMPLETE ===\n"
        f"Total: {len(summary)} PDFs ({len(succeeded)} ok, {len(failed)} failed)"
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
        "--pdf",
        action="append",
        type=Path,
        help="Extra PDF path(s) outside the school corpus; repeatable.",
    )
    parser.add_argument(
        "--ocr-engine",
        choices=("rapidocr_vi", "pp_structure"),
        default="rapidocr_vi",
        help="OCR backend. Default rapidocr_vi (RapidOCR + PP-OCRv6 Vietnamese).",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Delete existing rows that share the same document_number "
            "before re-ingesting. Use this to backfill the production "
            "schema when previous side-script runs left page-level "
            "sections in place."
        ),
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help=(
            "Skip Qdrant upsert. Useful when benching the parser / "
            "section / chunk pipeline without OpenAI / Qdrant creds."
        ),
    )
    parser.add_argument(
        "--approved-by",
        type=str,
        default="ocr-reingest@local",
        help="Operator name recorded as ingest source for traceability.",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
