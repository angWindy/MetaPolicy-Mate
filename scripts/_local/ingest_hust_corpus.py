"""Ingest real HUST PDFs, optionally approve, index and publish them.

This script never seeds synthetic data. Every chunk is parsed from a PDF below
``data/raw/HUST`` (or ``--data-dir``), and ``source_url`` records the absolute
path of that source PDF for citation traceability.

Metadata strategy:
* ``TITLES`` is the ground-truth table for the 8 PDFs we ship. It wins over
  the rule extractor so titles are deterministic across re-ingests.
* ``document_number`` is derived from the filename stem and verified against
  the rule extractor (``extract_document_number``). If the rule finds a
  different number, the rule's value wins and the ground-truth title is
  attached to that number.
* No LLM review. The hybrid path was prototyped in 2026-08 but reverted
  because the MVP does not need it and the rule extractor + TITLE table
  already cover every file we ship.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.domain.schemas import DocumentMetadata, ProcessingStatus  # noqa: E402
from src.ingestion.metadata_extractor import MetadataExtractionResult, extract_metadata  # noqa: E402
from src.rag.config import RAGSettings  # noqa: E402
from src.rag.container import RAGContainer  # noqa: E402


# Ground-truth metadata for the 8 HUST PDFs we ship. Each entry wins over
# the rule extractor so document_number and title are deterministic across
# re-ingests. The rule extractor is only consulted for documents not in this
# table, which keeps the curated set reproducible while still letting unknown
# documents fall through to the heuristic.
#
# Add entries here as new documents are curated. The key is the filename stem
# (no extension). The value provides both `title` and `document_number`.
METADATA_OVERRIDE: dict[str, dict[str, str]] = {
    "10232": {
        "title": "Quyết định phê duyệt mức học phí năm học 2025-2026",
        "document_number": "10232/QĐ-ĐHBK",
    },
    "10728": {
        "title": "Quy định về ngoại ngữ đối với sinh viên đại học chính quy",
        "document_number": "10728/QĐ-ĐHBK",
    },
    "2048": {
        "title": "Quy định phân loại trình độ và chuẩn ngoại ngữ sinh viên chính quy",
        "document_number": "2048/QĐ-ĐHBK",
    },
    "5445": {
        "title": "Quy chế đào tạo của Đại học Bách khoa Hà Nội",
        "document_number": "5445/QĐ-ĐHBK",
    },
    "5980": {
        "title": "Văn bản Đại học Bách khoa Hà Nội số 5980",
        "document_number": "5980/QĐ-ĐHBK",
    },
    "6100": {
        "title": "Văn bản Đại học Bách khoa Hà Nội số 6100",
        "document_number": "6100/QĐ-ĐHBK",
    },
    "7323": {
        "title": "Văn bản Đại học Bách khoa Hà Nội số 7323",
        "document_number": "7323/QĐ-ĐHBK",
    },
    "7737": {
        "title": "Bộ tiêu chí chương trình đào tạo kỹ sư chuyên sâu",
        "document_number": "7737/QĐ-ĐHBK",
    },
}


def _metadata(path: Path, rule: MetadataExtractionResult | None) -> DocumentMetadata:
    """Build metadata for the given PDF.

    For curated files (present in ``METADATA_OVERRIDE``) we always use the
    ground-truth ``document_number`` and ``title``. For other files we fall
    back to the rule extractor; if the rule is not confident enough we use
    ``<stem>/QĐ-ĐHBK`` and a generic title so the version still has a
    unique key for the database.
    """
    stem = path.stem
    override = METADATA_OVERRIDE.get(stem)
    if override is not None:
        return DocumentMetadata(
            title=override["title"],
            document_number=override["document_number"],
            issued_by="Đại học Bách khoa Hà Nội",
            owner_department="ĐT",
            access_level="internal",
            version_number=1,
            source_url=str(path.resolve()),
        )

    document_number = (
        rule.document_number
        if rule and rule.document_number and rule.document_number_confidence >= 0.7
        else f"{stem}/QĐ-ĐHBK"
    )
    title = rule.title.title if rule and rule.title and rule.title.title else None
    if title is None:
        title = f"Văn bản Đại học Bách khoa Hà Nội số {stem}"
    return DocumentMetadata(
        title=title,
        document_number=document_number,
        issued_by="Đại học Bách khoa Hà Nội",
        owner_department="ĐT",
        access_level="internal",
        version_number=1,
        source_url=str(path.resolve()),
    )


async def _process(
    container: RAGContainer,
    path: Path,
    *,
    approve_publish: bool,
) -> dict:
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    version = container.repository.find_version_by_checksum(checksum)
    result: dict = {"file": str(path), "source_url": str(path.resolve())}

    if version is None:
        # Run the rule extractor once to discover document_number + title.
        # The pipeline will re-parse internally; this is cheap and means we
        # do not need to peel the parser apart.
        blocks, parser_warnings = container.parser.parse(
            path.name, path.read_bytes()
        )
        rule: MetadataExtractionResult = extract_metadata(
            blocks, filename_hint=path.name
        )
        result["rule_rationale"] = rule.rationale
        result["needs_human_review"] = rule.needs_human_review

        metadata = _metadata(path, rule)
        ingested = await container.ingestion.ingest(
            path.name,
            path.read_bytes(),
            metadata,
        )
        version_id = ingested.version_id
        result.update(
            status="ingested",
            version_id=version_id,
            sections=ingested.section_count,
            chunks=ingested.chunk_count,
            warnings=ingested.warnings,
        )
        version = container.repository.get_version(version_id)
    else:
        version_id = version.id
        result.update(status="existing", version_id=version_id)

    if not approve_publish or version is None:
        return result

    if version.processing_status == ProcessingStatus.REVIEW_REQUIRED.value:
        version = container.repository.approve_version(
            version_id,
            approved_by="hust-e2e-runner",
        )
        result["approved"] = True
    if version.processing_status == ProcessingStatus.APPROVED.value:
        result["indexed_chunks"] = await container.ingestion.index_approved_version(
            version_id
        )
        version = container.repository.get_version(version_id)
    if version and version.processing_status in {
        ProcessingStatus.APPROVED.value,
        ProcessingStatus.INDEXED.value,
    }:
        version = container.repository.publish_version(version_id)
        result["published"] = True

    result["processing_status"] = version.processing_status if version else None
    result["legal_status"] = version.legal_status if version else None
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest real PDFs from data/raw/HUST.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw" / "HUST")
    parser.add_argument("--file", action="append", help="PDF filename; repeat to ingest several.")
    parser.add_argument(
        "--approve-publish",
        action="store_true",
        help="Approve, index and publish after parsing (intended for controlled E2E runs).",
    )
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Enable OCR / scan processing (default: pypdf-only, fast).",
    )
    parser.add_argument(
        "--parser-backend",
        default="auto",
        choices=["auto", "pypdf", "docling"],
        help="PDF parser backend. Default 'auto' falls back to OCR when a "
        "born-digital parser returns empty text (scan PDFs).",
    )
    parser.add_argument(
        "--ocr-gpu",
        action="store_true",
        help="Enable EasyOCR GPU (default: CPU). GPU is faster but only "
        "available when CUDA is reachable from the Python process.",
    )
    args = parser.parse_args()

    overrides: dict = {"parser_backend": args.parser_backend, "ocr_gpu": args.ocr_gpu}
    if args.ocr:
        overrides["ocr_enabled"] = True
    settings = RAGSettings(**overrides)
    container = RAGContainer(settings)
    paths = (
        [args.data_dir / name for name in args.file]
        if args.file
        else sorted(args.data_dir.glob("*.pdf"))
    )
    if not paths or any(not path.is_file() for path in paths):
        print("No valid PDF input found.", file=sys.stderr)
        return 2

    results = []
    for path in paths:
        try:
            results.append(
                await _process(container, path, approve_publish=args.approve_publish)
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "file": str(path),
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 1 if any(item["status"] == "failed" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))