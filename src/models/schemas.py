from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from src.domain.schemas import Citation, EvidenceAction, RetrievalStatus
from src.guardrails.contracts import GuardrailDecision


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    as_of_date: date | None = Field(
        default=None,
        description="Ngày hiệu lực dùng để lọc phiên bản tài liệu; mặc định là ngày hiện tại.",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Câu trả lời đã qua evidence gate và kiểm tra citation")
    citations: list[Citation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: str = "low"
    request_id: str
    evidence_status: RetrievalStatus | None = None
    evidence_action: EvidenceAction | None = None
    guardrail_action: str | None = None
    guardrail_stage: str | None = None
    guardrail_reason_codes: list[str] = Field(default_factory=list)
    guardrail_policy_version: str | None = None
    guardrail_events: list[GuardrailDecision] = Field(default_factory=list)
