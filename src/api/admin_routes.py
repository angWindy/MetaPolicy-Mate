from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.routes import get_rag_request_context, RAGRequestContext
from src.domain.schemas import DocumentMetadata
from src.ingestion.document_number import AUTO_DETECT_SENTINEL


admin_router = APIRouter(tags=["admin"])


def _require_data_owner(context: RAGRequestContext) -> None:
    roles = context.identity.assigned_roles
    if not {"data_owner", "security_admin"}.intersection(roles):
        raise HTTPException(
            status_code=403,
            detail="Role data_owner or security_admin is required.",
        )


def _validate_metadata_for_ingest(metadata: DocumentMetadata) -> None:
    """Reject metadata values that would confuse the ingestion pipeline.

    The auto-detect sentinel is reserved for internal batch jobs that drive
    ingestion programmatically. The HTTP admin route must always receive a
    real document number so data owners see what they typed in the audit
    trail instead of having the pipeline silently rewrite it.
    """
    if metadata.document_number == AUTO_DETECT_SENTINEL:
        raise HTTPException(
            status_code=422,
            detail=(
                "`document_number` không được đặt bằng giá trị tạm của hệ thống."
                " Vui lòng nhập số hiệu văn bản thật trước khi ingest qua API."
            ),
        )


@admin_router.post("/admin/documents/ingest")
async def ingest_document(
    file: Annotated[UploadFile, File(...)],
    metadata_json: Annotated[str, Form(...)],
    context: RAGRequestContext = Depends(get_rag_request_context),
):
    _require_data_owner(context)
    try:
        metadata = DocumentMetadata.model_validate_json(metadata_json)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid metadata: {exc}") from exc
    _validate_metadata_for_ingest(metadata)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload.")
    try:
        result = await context.container.ingestion.ingest(
            filename=file.filename or "upload.bin",
            content=content,
            metadata=metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "document_id": result.document_id,
        "version_id": result.version_id,
        "processing_status": result.processing_status.value,
        "section_count": result.section_count,
        "chunk_count": result.chunk_count,
        "warnings": result.warnings,
    }


@admin_router.post("/admin/documents/{version_id}/approve")
async def approve_version(
    version_id: str,
    context: RAGRequestContext = Depends(get_rag_request_context),
):
    _require_data_owner(context)
    try:
        version = context.container.repository.approve_version(
            version_id, approved_by=context.identity.user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "version_id": version.id,
        "processing_status": version.processing_status,
        "approved_by": version.approved_by,
    }


@admin_router.post("/admin/documents/{version_id}/publish")
async def publish_version(
    version_id: str,
    context: RAGRequestContext = Depends(get_rag_request_context),
):
    _require_data_owner(context)
    try:
        version = context.container.repository.publish_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "version_id": version.id,
        "processing_status": version.processing_status,
        "legal_status": version.legal_status,
    }


@admin_router.post("/admin/documents/{version_id}/index")
async def index_version(
    version_id: str,
    context: RAGRequestContext = Depends(get_rag_request_context),
):
    """Index an APPROVED version into Qdrant and promote it to INDEXED.

    Required step between Approve and Publish. If the embed/upsert step
    fails, the version stays at APPROVED and the error message is returned
    so the operator can retry without losing the approval decision.
    """
    _require_data_owner(context)
    try:
        count = await context.container.ingestion.index_approved_version(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Indexing failed mid-flight; status stays at APPROVED.
        raise HTTPException(
            status_code=502,
            detail=f"Index thất bại; phiên bản vẫn ở trạng thái APPROVED. Lỗi: {exc}",
        ) from exc
    return {
        "version_id": version_id,
        "indexed_chunks": count,
        "processing_status": "indexed",
    }


@admin_router.post("/admin/index/reindex")
async def reindex(context: RAGRequestContext = Depends(get_rag_request_context)):
    _require_data_owner(context)
    context.container.repository.refresh_current_legal_statuses()
    count = await context.container.warm_index()
    return {"indexed_chunks": count}


@admin_router.get("/admin/stats")
async def stats(context: RAGRequestContext = Depends(get_rag_request_context)):
    _require_data_owner(context)
    return context.container.repository.stats()