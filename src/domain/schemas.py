from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
SafeLimit = Annotated[int, Field(ge=1, le=100)]
PositiveRank = Annotated[int, Field(ge=1)]
NonNegativeMilliseconds = Annotated[float, Field(ge=0.0)]


class ProcessingStatus(StrEnum):
    """Canonical English processing status (source of truth).

    The legacy module ``src.domain.enums.document_processing_status``
    re-exports these values; new code MUST import from this file
    directly.

    Vietnamese member names (``CHO_XU_LY_NOI_DUNG``, ``DANG_SO_HOA``,
    ``DA_SO_HOA``, ``SO_HOA_THAT_BAI``) are aliased to the canonical
    English values so existing call sites keep working.
    """

    RECEIVED = "received"
    QUEUED = "queued"
    QUARANTINED = "quarantined"
    PARSED = "parsed"
    REVIEW_REQUIRED = "review_required"
    PENDING_REVIEW = "pending_review"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    INDEXED = "indexed"
    PUBLISHED = "published"
    FAILED = "failed"

    # Legacy Vietnamese aliases - DO NOT use in new code.
    CHO_XU_LY_NOI_DUNG = RECEIVED
    DANG_SO_HOA = PARSED
    DA_SO_HOA = INDEXED
    SO_HOA_THAT_BAI = FAILED

    @classmethod
    def _missing_(cls, value: object) -> "ProcessingStatus | None":
        # Tolerate legacy / external values by mapping to a safe default.
        # Legacy DB string "Published" maps to INDEXED (the closest canonical value).
        legacy_map = {
            "Published": cls.INDEXED,
            "published": cls.PUBLISHED,
            "indexed": cls.INDEXED,
            "approved": cls.APPROVED,
        }
        if isinstance(value, str):
            return legacy_map.get(value)
        return None


class LegalStatus(StrEnum):
    """Canonical English legal status (source of truth).

    Vietnamese member names (``CHO_XU_LY_NOI_DUNG``, ``DANG_HIEU_LUC``,
    ``BI_THAY_THE``, ``HET_HIEU_LUC``) are aliased to the canonical
    English values so existing call sites keep working.
    """

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REVOKED = "revoked"

    # Legacy Vietnamese aliases - DO NOT use in new code.
    CHO_XU_LY_NOI_DUNG = DRAFT
    DANG_HIEU_LUC = EFFECTIVE
    BI_THAY_THE = SUPERSEDED
    HET_HIEU_LUC = EXPIRED


class NotificationType(StrEnum):
    """Canonical notification types (source of truth)."""

    DOCUMENT_PENDING_REVIEW = "document.pending_review"
    DOCUMENT_PENDING_APPROVAL = "document.pending_approval"
    DOCUMENT_APPROVED = "document.approved"
    DOCUMENT_REJECTED = "document.rejected"
    DOCUMENT_PUBLISHED = "document.published"


class AccessScope(StrEnum):
    """Canonical access scope for the data-level document ACL (2-value).

    Used by ``DocumentMetadata.access_level`` and the underlying
    ``documents.access_scope`` DB column to encode which departments may
    read a document. The classification (PUBLIC/INTERNAL/CONFIDENTIAL/
    RESTRICTED) is tracked separately via ``ClassificationLevel`` and
    never persisted in the document row.

    Values are UPPERCASE to match the database column (the authoritative
    store). All production consumers use ``src.domain.enums.document_access_scope.DocumentAccessScope``
    which carries the same values; this enum in ``schemas.py`` is the
    canonical source of truth for Pydantic models and domain logic.
    """

    PUBLIC = "PUBLIC"
    DEPARTMENT = "DEPARTMENT"

    @classmethod
    def _missing_(cls, value: object) -> "AccessScope | None":
        # Backward-compat: accept lowercase strings that may still exist
        # in some DB rows or test fixtures from before the 2026-09-01 fix.
        if isinstance(value, str) and value.lower() in ("public", "department"):
            return cls(value.upper())
        return None


class RetrievalStatus(StrEnum):
    SUFFICIENT = "sufficient"
    PARTIAL = "partial"
    WEAK = "weak"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    CONFLICT = "conflict"


class EvidenceAction(StrEnum):
    GENERATE = "generate"
    RETRY = "retry"
    ABSTAIN = "abstain"
    HUMAN_ESCALATION = "human_escalation"


class ContextRole(StrEnum):
    WINNING = "winning"
    SUPPORTING_CONTEXT = "supporting_context"


class ContextExpansionType(StrEnum):
    WINNING = "winning"
    PARENT_HEADING = "parent_heading"
    PARENT_CHUNK = "parent_chunk"
    PREVIOUS_CHUNK = "previous_chunk"
    NEXT_CHUNK = "next_chunk"
    REFERENCED_DEFINITION = "referenced_definition"


class CitationKind(StrEnum):
    WINNING = "winning"
    EXPANDED = "expanded"


class QueryType(StrEnum):
    IDENTIFIER = "identifier"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    MIXED = "mixed"
    MULTI_INTENT = "multi_intent"


class ClassificationLevel(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class UserContext(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "user-123",
                    "tenant_id": "hust",
                    "department": "TCCB",
                    "roles": ["staff"],
                    "clearance_level": "internal",
                }
            ]
        }
    )

    user_id: NonEmptyString
    tenant_id: NonEmptyString = "public"
    department: NonEmptyString = "PUBLIC"
    roles: set[str] = Field(default_factory=lambda: {"staff"})
    clearance_level: ClassificationLevel = ClassificationLevel.INTERNAL

    @field_validator("user_id", "tenant_id", "department")
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("User context identifiers must not be blank.")
        return value

    def has_any_role(self, *roles: str) -> bool:
        return bool(self.roles.intersection(roles))


class DocumentMetadata(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    document_number: str = Field(min_length=1, max_length=200)
    issued_by: str = Field(default="Đại học Bách khoa Hà Nội", max_length=500)
    owner_department: str = Field(min_length=1, max_length=200)
    issued_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    # Data-level ACL (PUBLIC/DEPARTMENT only).
    access_level: AccessScope = AccessScope.PUBLIC
    allowed_departments: list[str] = Field(default_factory=list)
    version_number: int = Field(default=1, ge=1)
    replaces_version_id: str | None = None
    source_url: str | None = None
    @field_serializer("issued_date", "effective_from", "effective_to")
    def serialize_date(self, value: date | None) -> str | None:
        """Return dates in a JSON/SQLAlchemy JSON compatible form."""
        return value.isoformat() if value else None

    @field_serializer("access_level")
    def serialize_access_level(self, value: AccessScope) -> str:
        """Persist the enum value instead of the Python enum instance."""
        return value.value
    @model_validator(mode="after")
    def validate_dates_and_scope(self) -> DocumentMetadata:
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Ngày hết hiệu lực phải sau ngày bắt đầu hiệu lực.")
        if self.access_level == AccessScope.DEPARTMENT and not self.allowed_departments:
            raise ValueError("Văn bản cấp phòng/ban phải khai báo allowed_departments.")
        return self


class ParsedBlock(BaseModel):
    text: str
    page: int | None = None
    block_index: int = 0
    block_type: str | None = None  # 'text' | 'heading' | 'table' | 'list_item'
    heading_path: list[str] = Field(default_factory=list)
    # Origin of the block — distinguishes text-vs-table extraction, or
    # cross-format ingestion (pdfplumber vs docx vs txt). Set by the
    # parser layer via ``model_copy(update={"source": ...})``.
    source: str | None = None
    # Average OCR confidence for the page this block came from. Populated
    # by the PDF processor for OCR / hybrid pages (``None`` for native
    # digital pages). ``extract_sections(ocr_mode=True)`` routes blocks
    # below the low-confidence threshold to a semantic-chunking fallback
    # so regex-based heading detection doesn't shred a low-quality scan.
    page_avg_confidence: float | None = None
    low_confidence: bool = False

    @classmethod
    def from_native_text(
        cls,
        text: str,
        page: int | None = None,
        block_index: int = 0,
        block_type: str | None = None,
        heading_path: list[str] | None = None,
        **_unused: Any,
    ) -> "ParsedBlock":
        """Factory accepting the wide kwargs shape produced by upstream parsers.

        The various parsers (PyMuPDF, RapidOCR, PDFPlumber) pass slightly
        different keyword names. Anything we don't have an explicit field
        for is silently dropped via ``**_unused``.
        """
        return cls(
            text=text,
            page=page,
            block_index=block_index,
            block_type=block_type,
            heading_path=heading_path or [],
        )

    @classmethod
    def from_ocr_block(
        cls,
        ocr_block: Any,
        block_index: int = 0,
        *,
        page_avg_confidence: float | None = None,
        low_confidence_threshold: float = 0.6,
    ) -> "ParsedBlock":
        """Factory for OCR-derived blocks.

        Mirrors :meth:`from_native_text` but accepts an ``OCRBlock`` (or
        any duck-typed object exposing ``text``, ``page``, ``block_type``,
        ``confidence``). Two fields get populated here:

        * ``page_avg_confidence`` — the parent page's average OCR
          confidence. Used downstream to decide whether regex-based
          heading detection is trustworthy.
        * ``low_confidence`` — ``True`` when ``page_avg_confidence`` is
          below ``low_confidence_threshold``. ``extract_sections`` skips
          blocks with this flag and routes them to the semantic-chunking
          fallback (``ocr_mode=True``).

        The factory accepts the ``OCRBlock`` Pydantic model lazily via a
        duck-typed ``Any`` to avoid an import cycle — the caller already
        has the OCR block in scope.
        """
        block_type_value = None
        raw_block_type = getattr(ocr_block, "block_type", None)
        if raw_block_type is not None:
            block_type_value = getattr(raw_block_type, "value", None) or str(raw_block_type)

        confidence = float(getattr(ocr_block, "confidence", 1.0) or 0.0)
        is_low = (
            page_avg_confidence is not None
            and page_avg_confidence < low_confidence_threshold
        )
        return cls(
            text=str(getattr(ocr_block, "text", "") or ""),
            page=getattr(ocr_block, "page", None),
            block_index=block_index,
            block_type=block_type_value,
            heading_path=[],
            source="ocr",
            page_avg_confidence=(
                float(page_avg_confidence)
                if page_avg_confidence is not None
                else None
            ),
            low_confidence=is_low,
        )


class SectionData(BaseModel):
    """Cấu trúc pháp lý rời rạc: Chương, Mục, Điều, Khoản, Điểm, v.v."""

    heading_path: list[str] = Field(default_factory=list)
    section_type: str | None = None  # chapter | article | clause | point
    section_number: str | None = None  # "II", "5", "2", "a"
    heading: str | None = None  # "Điều 5. Cán bộ được nghỉ phép"
    page: int | None = None
    text: str
    # Set by ``extract_sections`` when the underlying block came from a
    # low-OCR-confidence page. The chunker copies this flag into the
    # chunk metadata so retrieval / UI can flag fragments that may need
    # human review.
    low_confidence: bool = False


class ChunkData(BaseModel):
    id: str
    text: str
    embedding_text: str
    document_id: str
    version_id: str
    section_id: str | None = None
    chunk_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "original_query": "Quy định nghỉ phép áp dụng cho ai?",
                    "user_context": {
                        "user_id": "user-123",
                        "department": "TCCB",
                        "roles": ["staff"],
                    },
                    "limit": 100,
                    "as_of_date": "2026-08-04",
                }
            ]
        }
    )

    original_query: NonEmptyString
    user_context: UserContext
    limit: SafeLimit = 100
    as_of_date: date | None = None

    @field_validator("original_query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Retrieval query must not be blank.")
        return value


class Candidate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "document-001",
                    "version_id": "version-002",
                    "content": "Điều 5. Cán bộ được nghỉ phép theo kế hoạch.",
                    "metadata": {"article": "5", "department": "TCCB"},
                    "dense_rank": 2,
                    "sparse_rank": 1,
                    "fusion_score": 0.0317,
                    "rerank_score": 0.91,
                }
            ]
        }
    )

    chunk_id: NonEmptyString
    document_id: NonEmptyString
    version_id: NonEmptyString
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    dense_rank: PositiveRank | None = None
    sparse_rank: PositiveRank | None = None
    fusion_score: float = Field(ge=0.0)
    rerank_score: float | None = None

    @field_validator("chunk_id", "document_id", "version_id")
    @classmethod
    def required_ids_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Candidate identifiers must not be blank.")
        return value


class Citation(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "document-001",
                    "version_id": "version-002",
                    "document_number": "01/QĐ-ĐHBK",
                    "title": "Quy định nghỉ phép",
                    "source": "01/QĐ-ĐHBK, Điều 5",
                    "article": "5",
                    "page": 3,
                    "source_url": "https://example.edu.vn/regulations/01",
                    "excerpt": "Cán bộ được nghỉ phép theo kế hoạch.",
                }
            ]
        }
    )

    chunk_id: NonEmptyString
    document_id: NonEmptyString
    version_id: NonEmptyString
    document_number: NonEmptyString
    title: NonEmptyString
    source: NonEmptyString
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    section: str | None = None
    page: int | None = None
    source_url: str | None = None
    excerpt: str = ""
    citation_kind: CitationKind = CitationKind.WINNING
    winning_chunk_id: NonEmptyString | None = None
    # Score from the cross-encoder reranker. Null when reranker is unavailable.
    # Frontend uses this to highlight low-quality chunks (e.g. score < 0.10).
    rerank_score: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("source")
    @classmethod
    def source_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Citation source must not be blank.")
        return value


class ContextSegment(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chunk_id": "chunk-001",
                    "document_id": "document-001",
                    "version_id": "version-002",
                    "content": "Điều 5. Cán bộ được nghỉ phép theo kế hoạch.",
                    "context_role": "winning",
                    "expansion_type": "winning",
                    "winning_chunk_id": "chunk-001",
                    "metadata": {"section": "Điều 5"},
                }
            ]
        }
    )

    chunk_id: NonEmptyString
    document_id: NonEmptyString
    version_id: NonEmptyString
    content: NonEmptyString
    context_role: ContextRole
    expansion_type: ContextExpansionType
    winning_chunk_id: NonEmptyString
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextWindow(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "segments": ContextSegment.model_config["json_schema_extra"][
                        "examples"
                    ],
                    "citations": Citation.model_config["json_schema_extra"][
                        "examples"
                    ],
                    "token_count": 42,
                    "token_budget": 3000,
                    "truncated": False,
                    "warnings": [],
                }
            ]
        }
    )

    segments: list[ContextSegment] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    token_budget: int = Field(ge=1)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class Latency(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "policy_filter_ms": 4.2,
                    "dense_ms": 18.1,
                    "sparse_ms": 7.4,
                    "fusion_ms": 0.8,
                    "rerank_ms": 42.0,
                    "evidence_gate_ms": 1.1,
                    "total_ms": 73.6,
                }
            ]
        }
    )

    policy_filter_ms: NonNegativeMilliseconds = 0.0
    dense_ms: NonNegativeMilliseconds = 0.0
    sparse_ms: NonNegativeMilliseconds = 0.0
    fusion_ms: NonNegativeMilliseconds = 0.0
    rerank_ms: NonNegativeMilliseconds = 0.0
    evidence_gate_ms: NonNegativeMilliseconds = 0.0
    total_ms: NonNegativeMilliseconds


class RetrievalResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "partial",
                    "original_query": "Quy định nghỉ phép áp dụng cho ai?",
                    "transformed_queries": [
                        "đối tượng áp dụng quy định nghỉ phép",
                        "quy định nghỉ phép cán bộ",
                    ],
                    "candidates": Candidate.model_config["json_schema_extra"]["examples"],
                    "warnings": ["Sparse retrieval returned fewer than 20 candidates."],
                    "latency": {"total_ms": 31.5},
                    "index_version": "regulations-2026-08-04",
                }
            ]
        }
    )

    status: RetrievalStatus
    original_query: NonEmptyString
    transformed_queries: list[NonEmptyString] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency: Latency
    index_version: NonEmptyString


class RerankRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "original_query": "Quy định nghỉ phép áp dụng cho ai?",
                    "candidates": Candidate.model_config["json_schema_extra"]["examples"],
                    "limit": 5,
                }
            ]
        }
    )

    original_query: NonEmptyString
    candidates: list[Candidate]
    limit: SafeLimit = 5


class RerankResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "sufficient",
                    "original_query": "Quy định nghỉ phép áp dụng cho ai?",
                    "candidates": Candidate.model_config["json_schema_extra"]["examples"],
                    "warnings": [],
                    "latency": {"rerank_ms": 42.0, "total_ms": 42.0},
                }
            ]
        }
    )

    status: RetrievalStatus
    original_query: NonEmptyString
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency: Latency


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "sufficient",
                    "original_query": "Quy định nghỉ phép áp dụng cho ai?",
                    "evidence_score": 0.88,
                    "selected_candidates": Candidate.model_config["json_schema_extra"]["examples"],
                    "citations": Citation.model_config["json_schema_extra"]["examples"],
                    "warnings": [],
                    "latency": {"evidence_gate_ms": 1.1, "total_ms": 1.1},
                }
            ]
        }
    )

    status: RetrievalStatus
    decision: EvidenceAction = EvidenceAction.ABSTAIN
    reason: NonEmptyString = "Evidence has not been evaluated."
    original_query: NonEmptyString
    evidence_score: float = Field(ge=0.0, le=1.0)
    top_score: float | None = None
    score_gap: float | None = None
    independent_sources: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    selected_candidates: list[Candidate] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    latency: Latency


class SparseVectorData(BaseModel):
    indices: list[int] = Field(min_length=1)
    values: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sparse_vector(self) -> SparseVectorData:
        if len(self.indices) != len(self.values):
            raise ValueError("Sparse vector indices and values must have equal length.")
        if any(index < 0 for index in self.indices):
            raise ValueError("Sparse vector indices must be non-negative.")
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("Sparse vector indices must be unique.")
        return self


class QdrantPayload(BaseModel):
    """Search-index metadata copied from PostgreSQL; never the source of truth."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tenant_id": "hust",
                    "document_id": "93ff79c2-9d4a-4fa2-acf7-b6d3c2a4feaa",
                    "version_id": "a9662952-e4fd-414f-9e47-d223fe57d7a4",
                    "chunk_id": "5b46421d-4394-4b2a-a3b1-d49f43455591",
                    "parent_chunk_id": None,
                    "previous_chunk_id": None,
                    "next_chunk_id": "6dc4878c-3d68-4624-a0a2-e3d0b464e999",
                    "owner_unit": "TCCB",
                    "allowed_roles": ["staff", "manager"],
                    "allowed_units": ["TCCB"],
                    "classification": "internal",
                    "status": "published",
                    "valid_from": "2026-01-01T00:00:00Z",
                    "valid_to": None,
                    "page": 3,
                    "section": "Điều 5",
                    "title": "Quy chế đào tạo tín chỉ",
                    "document_number": "10232/QĐ-ĐHBK",
                    "source_url": "https://example.com/docs/10232",
                    "content_hash": "sha256:0123456789abcdef",
                    "embedding_model": "text-embedding-3-small",
                    "embedding_version": "1",
                    "sparse_model": "hashed-lexical",
                    "sparse_version": "1",
                    "index_version": "regulations-2026-08-04",
                }
            ]
        }
    )

    tenant_id: NonEmptyString
    document_id: NonEmptyString
    version_id: NonEmptyString
    chunk_id: NonEmptyString
    parent_chunk_id: NonEmptyString | None = None
    previous_chunk_id: NonEmptyString | None = None
    next_chunk_id: NonEmptyString | None = None
    owner_unit: NonEmptyString | None = None
    allowed_roles: list[NonEmptyString] = Field(default_factory=list)
    allowed_units: list[NonEmptyString] = Field(default_factory=list)
    classification: NonEmptyString
    status: NonEmptyString
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    title: str | None = None
    document_number: str | None = None
    source_url: str | None = None
    content_hash: NonEmptyString
    embedding_model: NonEmptyString
    embedding_version: NonEmptyString
    sparse_model: NonEmptyString | None = None
    sparse_version: NonEmptyString | None = None
    index_version: NonEmptyString

    @model_validator(mode="after")
    def validate_validity_window(self) -> QdrantPayload:
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from.")
        return self


class QdrantPointInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "payload": QdrantPayload.model_config["json_schema_extra"]["examples"][0],
                    "dense_vector": [0.0, 0.1, 0.2],
                    "sparse_vector": {"indices": [10, 42], "values": [0.7, 0.3]},
                }
            ]
        }
    )

    payload: QdrantPayload
    dense_vector: list[float] = Field(min_length=1)
    sparse_vector: SparseVectorData


class GeneratedAnswer(BaseModel):
    answer: str
    cited_chunk_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: str = "low"


class IngestionResult(BaseModel):
    document_id: str
    version_id: str
    processing_status: ProcessingStatus
    section_count: int
    chunk_count: int
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
