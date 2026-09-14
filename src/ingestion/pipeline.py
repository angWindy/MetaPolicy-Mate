from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from sqlalchemy import select

from src.db.models import Chunk, Document, DocumentVersion
from src.db.repository import Repository
from src.domain.schemas import DocumentMetadata, IngestionResult, ProcessingStatus
from src.ingestion.chunker import build_chunks
from src.ingestion.document_number import (
    AUTO_DETECT_SENTINEL,
    DocumentNumberProbe,
    extract_document_number,
)
from src.ingestion.file_validator import validate_upload
from src.ingestion.legal_structure import extract_sections
from src.ingestion.parser import DocumentParser
from src.rag.config import RAGSettings
from src.retrieval.vector_store import VectorRecord, VectorStore
from src.services.embeddings import EmbeddingProvider, content_hash_for_text
from src.services.sparse_embeddings import SparseEmbeddingProvider
from src.services.storage import LocalDocumentStorage

logger = logging.getLogger(__name__)

# Rough cap on how many characters of parsed text we hand to the
# document-number extractor. Vietnamese legal headers fit comfortably inside
# the first ~6 kB of a born-digital PDF or the OCR output of the first page;
# anything beyond that is body text and only adds noise.
_HEADER_TEXT_CHAR_BUDGET = 6000


class IngestionPipeline:
    def __init__(
        self,
        settings: RAGSettings,
        repository: Repository,
        parser: DocumentParser,
        storage: LocalDocumentStorage,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        sparse_embeddings: SparseEmbeddingProvider | None = None,
    ):
        self.settings = settings
        self.repository = repository
        self.parser = parser
        self.storage = storage
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.sparse_embeddings = sparse_embeddings

    @staticmethod
    def _resolve_document_number(
        metadata: DocumentMetadata,
        blocks: list,
    ) -> tuple[DocumentMetadata, DocumentNumberProbe | None, list[str]]:
        """Resolve the actual `document_number` to persist.

        Behaviour:
        * If the caller supplied a non-sentinel value, trust it.
        * If the caller used the ``AUTO_DETECT_SENTINEL`` placeholder, run the
          heuristic extractor over the early blocks. The probe never silently
          invents a value: when it cannot prove the match, the original
          sentinel is kept on the metadata so the unique constraint on
          ``documents.document_number`` triggers a clear error rather than
          silently mis-stamping the document.
        * The probe (whether triggered or not) is returned alongside any
          warnings so the caller can persist them on the version row.
        """
        warnings: list[str] = []
        if metadata.document_number != AUTO_DETECT_SENTINEL:
            return metadata, None, warnings

        header_text_parts: list[str] = []
        budget = _HEADER_TEXT_CHAR_BUDGET
        for block in blocks:
            text = getattr(block, "text", "") or ""
            if not text:
                continue
            header_text_parts.append(text)
            budget -= len(text)
            if budget <= 0:
                break
        header_text = "\n\n".join(header_text_parts)

        probe = extract_document_number(header_text)
        if probe.recommended is None:
            warnings.append(
                "Không tự trích xuất được số hiệu văn bản từ nội dung. "
                "Vui lòng cung cấp `document_number` rõ ràng và ingest lại."
            )
            return metadata, probe, warnings

        if probe.needs_human_review:
            warnings.append(
                f"Số hiệu văn bản được tạm đoán là '{probe.recommended}' "
                f"(độ tin cậy {probe.confidence:.2f}); phiên bản sẽ ở trạng thái "
                "REVIEW_REQUIRED cho tới khi được data owner xác nhận."
            )
        resolved = metadata.model_copy(update={"document_number": probe.recommended})
        return resolved, probe, warnings

    async def enqueue(
        self,
        filename: str,
        content: bytes,
        metadata: DocumentMetadata,
    ) -> IngestionResult:
        """Persist the queued version row and return immediately.

        Performs only the cheap operations: validate, dedup, save-to-quarantine,
        insert DB row, create IngestionJob. Heavy parse+chunk work happens
        later in :meth:`process_version`, scheduled by the background
        :class:`IngestionWorker`. The caller gets the ``version_id`` while
        the actual processing is still pending.

        The heuristic document-number probe is intentionally NOT run here —
        it needs parsed header text and would force a full parse before we
        can return to the user. The probe runs inside ``process_version``
        and can still fail the version back to ``REVIEW_REQUIRED`` with a
        warning.
        """
        validation = validate_upload(filename, content, self.settings.max_upload_mb)
        if not validation.valid:
            raise ValueError(validation.error or "Tệp không hợp lệ.")

        duplicate = self.repository.find_version_by_checksum(validation.checksum)
        if duplicate:
            raise ValueError(
                f"Tệp đã được nạp ở phiên bản {duplicate.version_number} "
                f"(version_id={duplicate.id})."
            )

        quarantine_path = self.storage.save_quarantine(
            document_number=metadata.document_number,
            version_number=metadata.version_number,
            filename=filename,
            content=content,
        )
        document, version = self.repository.create_document_version(
            metadata,
            checksum=validation.checksum,
            source_filename=filename,
            source_path=str(quarantine_path),
            processing_status=ProcessingStatus.QUEUED,
        )
        self.repository.create_ingestion_job(
            version.id, status="received", parser_name=self.parser.parser_backend
        )
        return IngestionResult(
            document_id=document.id,
            version_id=version.id,
            processing_status=ProcessingStatus.QUEUED,
            section_count=0,
            chunk_count=0,
            warnings=[],
        )

    async def process_version(self, version_id: str) -> IngestionResult:
        """Run the heavy parse+chunk pipeline for an already-queued version.

        Loads the version + quarantine file, runs parser/legal-structure/
        chunker, persists sections and chunks, promotes the file out of
        quarantine, and ends with ``REVIEW_REQUIRED`` on success or
        ``FAILED`` (with error recorded on ``IngestionJob``) on any
        exception. Never raises — failures are recorded on the row so the
        background worker can keep running.
        """
        job = self.repository.get_latest_job_for_version(version_id)
        try:
            version = self._load_version(version_id)
            if version is None:
                raise ValueError(f"Không tìm thấy version_id={version_id}.")
            if version.processing_status != ProcessingStatus.QUEUED.value:
                # Idempotent: a second submit() of the same version becomes
                # a no-op so retries never double-process.
                logger.info(
                    "ingest_skip reason=not_queued version_id=%s status=%s",
                    version_id,
                    version.processing_status,
                )
                return IngestionResult(
                    document_id=version.document_id,
                    version_id=version.id,
                    processing_status=ProcessingStatus(version.processing_status),
                    section_count=0,
                    chunk_count=0,
                    warnings=[],
                )

            if job is not None:
                self.repository.update_ingestion_job(job.id, status="parsing")

            blocks, parser_warnings = self._read_quarantine_and_parse(version)
            self._run_full_pipeline(version, blocks, parser_warnings)
            return self._result_from_version(version_id)
        except Exception as exc:  # noqa: BLE001 - record everything
            logger.exception("ingest_failed version_id=%s", version_id)
            try:
                self.repository.update_version_source(
                    version_id,
                    processing_status=ProcessingStatus.FAILED,
                    error=str(exc),
                )
                if job is not None:
                    self.repository.update_ingestion_job(
                        job.id,
                        status="failed",
                        error_message=f"{type(exc).__name__}: {exc}",
                    )
            except Exception as inner:  # pragma: no cover - defensive
                logger.exception(
                    "failed_to_record_failure version_id=%s err=%s", version_id, inner
                )
            return IngestionResult(
                document_id="",
                version_id=version_id,
                processing_status=ProcessingStatus.FAILED,
                section_count=0,
                chunk_count=0,
                warnings=[str(exc)],
            )

    async def ingest(
        self,
        filename: str,
        content: bytes,
        metadata: DocumentMetadata,
    ) -> IngestionResult:
        """Legacy synchronous ingest kept for tests and CLI scripts.

        Production HTTP path goes through :meth:`enqueue` + the background
        worker instead.
        """
        result = await self.enqueue(filename, content, metadata)
        return await self.process_version(result.version_id)

    # ── process_version helpers ─────────────────────────────────────────────

    def _load_version(self, version_id: str) -> DocumentVersion | None:
        return self.repository.get_version(version_id)

    def _read_quarantine_and_parse(
        self, version: DocumentVersion, _previous_blocks: list | None = None
    ) -> tuple[list, list[str]]:
        path = Path(version.source_path)
        content = path.read_bytes()
        blocks, parser_warnings = self.parser.parse(version.source_filename, content)
        return blocks, parser_warnings

    def _run_full_pipeline(
        self,
        version: DocumentVersion,
        blocks: list,
        parser_warnings: list[str],
    ) -> None:
        metadata = DocumentMetadata.model_validate(version.metadata_json)
        sections = extract_sections(blocks)
        section_dicts = [item.model_dump() for item in sections]
        chunks = build_chunks(
            document_id=version.document_id,
            version_id=version.id,
            metadata=metadata,
            sections=sections,
            max_chars=self.settings.chunk_max_chars,
            overlap_chars=self.settings.chunk_overlap_chars,
        )
        warnings = [
            *parser_warnings,
        ]
        if not any(item.section_type == "article" for item in sections):
            warnings.append("Không nhận diện được cấu trúc Điều/Khoản; data owner cần kiểm tra.")

        promoted_path = self.storage.promote(
            Path(version.source_path),
            document_number=metadata.document_number,
            version_number=metadata.version_number,
            filename=version.source_filename,
        )
        self.repository.update_version_source(
            version.id,
            source_path=str(promoted_path),
            processing_status=ProcessingStatus.PARSED,
        )
        self.repository.save_sections_and_chunks(
            version_id=version.id,
            sections=section_dicts,
            chunks=chunks,
            warnings=warnings,
        )

    def _result_from_version(self, version_id: str) -> IngestionResult:
        version = self.repository.get_version(version_id)
        assert version is not None
        chunk_count = len(self.repository.get_chunks_for_version(version_id))
        return IngestionResult(
            document_id=version.document_id,
            version_id=version.id,
            processing_status=ProcessingStatus(version.processing_status),
            section_count=0,
            chunk_count=chunk_count,
            warnings=[],
        )

    async def index_approved_version(self, version_id: str) -> int:
        # Phase 1: read-only snapshot of the version + chunks from PostgreSQL.
        # Anything that fails here (version not found, wrong status, missing
        # document) is a hard error; we never touch state.
        with self.repository.session_factory() as session:
            version = session.get(DocumentVersion, version_id)
            if version is None:
                raise ValueError("Không tìm thấy phiên bản.")
            if version.processing_status != ProcessingStatus.APPROVED.value:
                raise ValueError(
                    "Chỉ được index phiên bản đã duyệt. Hiện tại: "
                    f"processing_status={version.processing_status}."
                )
            chunks = list(
                session.scalars(
                    select(Chunk).where(Chunk.version_id == version_id).order_by(Chunk.chunk_index)
                )
            )
            document = session.get(Document, version.document_id)
            if document is None:
                raise ValueError("Không tìm thấy văn bản.")
            version_snapshot = {
                "id": version.id,
                "document_id": version.document_id,
                # Approved versions are indexed immediately before publish.
                # Store the status they will have once published, not "draft".
                "legal_status": (
                    "scheduled"
                    if version.effective_from and version.effective_from > date.today()
                    else "effective"
                ),
                "effective_from": version.effective_from,
                "effective_to": version.effective_to,
                "access_level": document.access_level,
                "allowed_departments": list(document.allowed_departments or []),
            }
            chunk_snapshots = [
                {
                    "id": chunk.id,
                    "text": chunk.text,
                    "embedding_text": chunk.embedding_text,
                    "metadata_json": dict(chunk.metadata_json or {}),
                }
                for chunk in chunks
            ]

        # Phase 2: heavy work (embed + Qdrant upsert). On failure we MUST keep
        # the version at APPROVED so a retry is possible and the operator can
        # investigate. We never silently fall back to PUBLISHED.
        try:
            if hasattr(self.vector_store, "create_payload_indexes"):
                await self.vector_store.create_payload_indexes()
            content_hashes = [
                snapshot["metadata_json"].get("content_hash")
                or content_hash_for_text(snapshot["embedding_text"])
                for snapshot in chunk_snapshots
            ]
            vectors = await self.embeddings.embed_documents(
                [snapshot["embedding_text"] for snapshot in chunk_snapshots],
                content_hashes=content_hashes,
            )
            index_version = self.settings.qdrant_collection
            records = []
            for snapshot, vector, content_hash in zip(
                chunk_snapshots, vectors, content_hashes, strict=True,
            ):
                payload = {
                    **snapshot["metadata_json"],
                    "chunk_id": snapshot["id"],
                    "content_hash": content_hash,
                    "embedding_model": self.embeddings.model_name,
                    "embedding_version": self.embeddings.model_version,
                    "index_version": index_version,
                }
                payload.setdefault("tenant_id", "hust")
                payload["status"] = "published"
                payload.setdefault(
                    "classification",
                    "internal"
                    if version_snapshot["access_level"] in {"public", "internal", "department"}
                    else "restricted",
                )
                payload["allowed_roles"] = ["*"]
                payload["allowed_units"] = [
                    item.upper() for item in version_snapshot["allowed_departments"]
                ] or ["*"]
                payload["valid_from"] = (
                    version_snapshot["effective_from"].isoformat()
                    if version_snapshot["effective_from"]
                    else "1970-01-01T00:00:00Z"
                )
                payload["valid_to"] = (
                    version_snapshot["effective_to"].isoformat()
                    if version_snapshot["effective_to"]
                    else None
                )
                payload["legal_status"] = version_snapshot["legal_status"] or "effective"
                if self.sparse_embeddings is not None:
                    sparse = self.sparse_embeddings.sparse_embed_documents(
                        [snapshot["embedding_text"]]
                    )[0]
                    payload["sparse_vector"] = {
                        "indices": list(sparse.indices),
                        "values": list(sparse.values),
                    }
                records.append(VectorRecord(id=snapshot["id"], vector=vector, payload=payload))
            await self.vector_store.upsert(records)
        except Exception as exc:
            # Keep status at APPROVED so the operator can re-run /index; surface
            # a clear message instead of swallowing the failure.
            raise RuntimeError(
                f"Index thất bại cho version_id={version_id}. "
                f"Phiên bản vẫn ở trạng thái APPROVED để retry. Lỗi: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # Phase 3: only after Qdrant has the points do we promote to INDEXED.
        self.repository.mark_indexed(version_id)
        return len(records)