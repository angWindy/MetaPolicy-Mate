from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class GuardrailAction(StrEnum):
    ALLOW = "allow"
    SANITIZE = "sanitize"
    BLOCK = "block"
    ABSTAIN = "abstain"
    HUMAN_REVIEW = "human_review"


class GuardrailStage(StrEnum):
    INPUT = "input"
    RETRIEVAL = "retrieval"
    OUTPUT = "output"


class GuardrailReason(StrEnum):
    DIRECT_PROMPT_INJECTION = "direct_prompt_injection"
    JAILBREAK_OR_PERSONA_OVERRIDE = "jailbreak_or_persona_override"
    ENCODED_PROMPT_INJECTION = "encoded_prompt_injection"
    PROMPT_OR_POLICY_EXTRACTION = "prompt_or_policy_extraction"
    RBAC_ESCALATION = "rbac_escalation"
    SECRET_EXFILTRATION = "secret_exfiltration"
    TOOL_OR_NETWORK_ABUSE = "tool_or_network_abuse"
    INPUT_TOO_LARGE = "input_too_large"
    EXCESSIVE_INPUT_LINES = "excessive_input_lines"
    EMPTY_AFTER_NORMALIZATION = "empty_after_normalization"
    CONTROL_CHARACTERS_REMOVED = "control_characters_removed"
    INDIRECT_PROMPT_INJECTION = "indirect_prompt_injection"
    EVIDENCE_TOO_LARGE = "evidence_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    OUTPUT_EMPTY = "output_empty"
    OUTPUT_SECRET_LEAK = "output_secret_leak"
    OUTPUT_PII_LEAK = "output_pii_leak"
    OUTPUT_PROMPT_LEAK = "output_prompt_leak"
    OUTPUT_UNVERIFIED = "output_unverified"


class GuardrailDecision(BaseModel):
    """Content-free decision safe for logs, API responses and checkpoints."""

    model_config = ConfigDict(extra="forbid")

    action: GuardrailAction
    stage: GuardrailStage
    reason_codes: list[GuardrailReason] = Field(default_factory=list)
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    policy_version: str = Field(min_length=1)
    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def blocks_processing(self) -> bool:
        return self.action in {
            GuardrailAction.BLOCK,
            GuardrailAction.ABSTAIN,
            GuardrailAction.HUMAN_REVIEW,
        }


@dataclass(frozen=True)
class TextInspection:
    normalized_text: str
    decision: GuardrailDecision


__all__ = [
    "GuardrailAction",
    "GuardrailDecision",
    "GuardrailReason",
    "GuardrailStage",
    "TextInspection",
]
