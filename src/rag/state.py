from __future__ import annotations

from datetime import date
from typing import TypedDict

from src.domain.schemas import Citation, EvidenceAction, RetrievalStatus, RetrievedChunk, UserContext


class RAGState(TypedDict, total=False):
    query: str
    rerank_query: str
    conversation_context: str
    user: UserContext
    as_of_date: date | None
    request_id: str
    retrieved_chunks: list[RetrievedChunk]
    answer: str
    citations: list[Citation]
    warnings: list[str]
    confidence: str
    error_code: str
    cited_chunk_ids: list[str]
    evidence_status: RetrievalStatus
    evidence_decision: EvidenceAction
    evidence_reason: str
    retry_count: int
