"""Bulk-ingest all PDFs under data/raw/ via the production ingestion pipeline.

Flow per PDF (mirrors the admin HTTP path):
    enqueue           -> create Document + DocumentVersion + IngestionJob rows
    process_version   -> parse PDF, build rag_legacy.chunks, save Section + Chunk rows
    approve_version   -> move processing_status to APPROVED
    index_approved    -> embed rag_legacy.chunks + upsert into Qdrant
    publish_version   -> set legal_status=EFFECTIVE for retrieval

Usage (run inside the backend container):
    python scripts/ingest_raw_pdfs.py
    python scripts/ingest_raw_pdfs.py --school HUCE
    python scripts/ingest_raw_pdfs.py --only 10232.pdf
"""
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.repository import Repository  # noqa: E402
from src.domain.schemas import AccessScope, DocumentMetadata  # noqa: E402
from src.rag.config import get_rag_settings  # noqa: E402
from src.rag.container import RAGContainer  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_DIR = PROJECT_ROOT / "data"


def discover_schools() -> list[str]:
    """Discover available school folders from data/raw/ at runtime.

    Scans the top-level directories under data/raw/ and returns any
    folder name that contains at least one PDF file. Falls back to an
    empty list if the directory is empty or missing — the caller will
    handle the empty case with a warning.
    """
    if not RAW_DIR.is_dir():
        return []
    schools: list[str] = []
    for entry in sorted(RAW_DIR.iterdir()):
        if not entry.is_dir():
            continue
        has_pdf = any(
            p.suffix.lower() == ".pdf" for p in entry.iterdir() if p.is_file()
        )
        if has_pdf:
            schools.append(entry.name.upper())
    return schools


def list_pdfs(school: str | None, only: str | None) -> list[Path]:
    paths: list[Path] = []
    # Dynamically discover schools from filesystem — no hard-coded list.
    available = discover_schools()
    if school:
        schools = [school.upper()]
        missing = [s for s in schools if s not in available]
        if missing:
            print(f"WARNING: school folder(s) not found under data/raw/: {missing}")
    else:
        schools = available
        if not schools:
            print("WARNING: no school folders with PDFs found under data/raw/")
    for s in schools:
        school_dir = RAW_DIR / s
        if not school_dir.is_dir():
            continue
        for p in sorted(school_dir.iterdir()):
            if p.suffix.lower() != ".pdf":
                continue
            if only and only not in p.name:
                continue
            paths.append(p)
    return paths


async def ingest_one(
    container: RAGContainer,
    repository: Repository,
    pdf_path: Path,
    school: str,
    approved_by: str,
) -> tuple[int, str]:
    raw_bytes = pdf_path.read_bytes()
    import hashlib  # noqa: PLC0415
    checksum = hashlib.sha256(raw_bytes).hexdigest()

    metadata = DocumentMetadata(
        document_number=f"RAW-{school}-{pdf_path.stem[:24]}",
        title=pdf_path.stem,
        version_number=1,
        effective_from=date.today(),
        effective_to=None,
        owner_department=school,
        access_level=AccessScope.DEPARTMENT,
        allowed_departments=[school, "HUCE", "HUST"],
        source_url=None,
    )

    # Reuse existing version (same checksum) if it has rag_legacy.chunks in the DB.
    existing = repository.find_version_by_checksum(checksum)
    status_value = existing.processing_status.value if existing and hasattr(existing.processing_status, "value") else (existing.processing_status if existing else None)
    chunks_exist = False
    if existing is not None:
        with repository.session_factory() as session:
            from sqlalchemy import func, select as sa_select  # noqa: PLC0415
            from src.db.models import Chunk as CK  # noqa: PLC0415

            n = session.scalar(
                sa_select(func.count(CK.id)).where(CK.version_id == existing.id)
            )
            chunks_exist = (n or 0) > 0
    if existing is not None and chunks_exist and status_value in {"published", "indexed", "approved", "parsed", "review_required"}:
        version_id = existing.id
        # Stamp tenant_id on every Chunk row so the Qdrant payload gets the
        # correct school (default upstream is "hust" for everyone).
        with repository.session_factory() as session:
            from sqlalchemy import text as sa_text  # noqa: PLC0415
            from src.db.models import DocumentVersion as DV  # noqa: PLC0415

            ver = session.get(DV, version_id)
            if ver is not None:
                md = dict(ver.metadata_json or {})
                md["tenant_id"] = school.lower()
                ver.metadata_json = md
                ver.processing_status = "approved"
                session.execute(
                    sa_text(
                        f"UPDATE rag_legacy.chunks SET metadata_json = metadata_json::jsonb || "
                        f"jsonb_build_object('tenant_id', '{school.lower()}') "
                        f"WHERE version_id = '{version_id}'"
                    )
                )
                session.commit()
        try:
            count = await container.ingestion.index_approved_version(version_id)
        except Exception as exc:  # noqa: BLE001
            return 0, f"  ! re-index failed: {exc}"
        try:
            repository.publish_version(version_id)
        except Exception as exc:  # noqa: BLE001
            return count, f"  -> re-indexed {count} chunks (publish failed: {exc})"
        return count, f"  -> re-indexed (legal_status=effective)"

    enqueue = await container.ingestion.enqueue(pdf_path.name, raw_bytes, metadata)
    if enqueue.version_id is None:
        return 0, "  ! enqueue returned no version_id"

    version_id = enqueue.version_id
    # Stamp tenant_id on the metadata_json so Qdrant payload carries the right school.
    with repository.session_factory() as session:
        from src.db.models import DocumentVersion as DV  # noqa: PLC0415

        ver = session.get(DV, version_id)
        if ver is not None:
            md = dict(ver.metadata_json or {})
            md["tenant_id"] = school.lower()
            ver.metadata_json = md
            session.commit()

    parse_result = await container.ingestion.process_version(version_id)
    if parse_result.processing_status.value in {"failed"}:
        return 0, f"  ! parse failed: {parse_result.warnings}"

    # Stamp tenant_id on every chunk so the Qdrant payload gets the right school.
    with repository.session_factory() as session:
        from sqlalchemy import text as sa_text  # noqa: PLC0415

        session.execute(
            sa_text(
                f"UPDATE rag_legacy.chunks SET metadata_json = metadata_json::jsonb || "
                f"jsonb_build_object('tenant_id', '{school.lower()}') "
                f"WHERE version_id = '{version_id}'"
            )
        )
        session.commit()

    try:
        repository.approve_version(version_id, approved_by)
    except Exception as exc:  # noqa: BLE001
        return 0, f"  ! approve failed: {exc}"

    try:
        await container.ingestion.index_approved_version(version_id)
    except Exception as exc:  # noqa: BLE001
        return 0, f"  ! index failed: {exc}"

    try:
        repository.publish_version(version_id)
    except Exception as exc:  # noqa: BLE001
        return 0, f"  ! publish failed: {exc}"

    with repository.session_factory() as session:
        from sqlalchemy import select, func  # noqa: PLC0415

        from src.db.models import Chunk, DocumentVersion  # noqa: PLC0415

        chunk_count = session.scalar(
            select(func.count(Chunk.id)).where(Chunk.version_id == version_id)
        )
        version = session.get(DocumentVersion, version_id)
        legal = version.legal_status if version else "?"
    return chunk_count or 0, f"  -> indexed (legal_status={legal})"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--school", choices=["HUCE", "HUST"], default=None)
    parser.add_argument("--only", default=None, help="substring to match filename")
    parser.add_argument("--limit", type=int, default=0, help="0 = no limit")
    args = parser.parse_args()

    settings = get_rag_settings()
    pdfs = list_pdfs(args.school, args.only)
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        print("No PDFs matched.")
        return

    print(f"=== Bulk ingest into Qdrant collection '{settings.qdrant_collection}' ===")
    print(f"target: {settings.qdrant_url}")
    print(f"embedding: {settings.embedding_provider}/{settings.embedding_model} "
          f"({settings.embedding_dimensions}-dim)")
    print(f"PDFs: {len(pdfs)}")
    print()

    container = RAGContainer(settings)
    repository = container.repository
    await container.vector_store.create_payload_indexes()

    total_chunks = 0
    failures = 0
    for idx, pdf in enumerate(pdfs, start=1):
        school = pdf.parts[pdf.parts.index("raw") + 1].upper()
        print(f"[{idx}/{len(pdfs)}] {school}: {pdf.name}")
        try:
            count, msg = await ingest_one(
                container,
                repository,
                pdf,
                school,
                approved_by="bulk_ingest_script",
            )
            print(msg)
            total_chunks += count
            if count == 0:
                failures += 1
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  !! FAILED: {exc}")

    print()
    print(f"Done. PDFs processed: {len(pdfs)}; chunks indexed: {total_chunks}; failures: {failures}")
    try:
        info = await container.vector_store.client.get_collection(settings.qdrant_collection)
        print(f"Qdrant points_count = {info.points_count}")
    except Exception as exc:  # noqa: BLE001
        print(f"(could not fetch collection stats: {exc})")


if __name__ == "__main__":
    asyncio.run(main())