from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

from src.domain.schemas import Candidate
from src.guardrails.contracts import (
    GuardrailAction,
    GuardrailDecision,
    GuardrailReason,
    GuardrailStage,
    TextInspection,
)

_INVISIBLE_OR_BIDI = re.compile(
    "[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\u00ad\u034f\u061c"
    "\u115f\u1160\u17b4\u17b5\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f"
    "\ufeff\ufff9-\ufffb]"
)
_BASE64_TOKEN = re.compile(r"(?<![A-Za-z0-9_+/=-])([A-Za-z0-9_+/-]{24,}={0,2})(?![A-Za-z0-9_+/=-])")
_HEX_TOKEN = re.compile(r"(?<![0-9A-Fa-f])((?:[0-9A-Fa-f]{2}){12,})(?![0-9A-Fa-f])")
_URL_ENCODED_RUN = re.compile(r"(?:%[0-9A-Fa-f]{2}){4,}")
_SPACED_LETTERS = re.compile(r"\b(?:[a-z]\s+){4,}[a-z]\b")
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "х": "x",
        "у": "y",
        "і": "i",
        "ј": "j",
        "đ": "d",
    }
)

_DIRECT_INJECTION = (
    re.compile(
        r"\b(ignore|disregard|forget|override|bypass|supersede)\b.{0,90}"
        r"\b(previous|prior|system|developer|hidden|instruction|rules?|policy|prompt)\b"
    ),
    re.compile(
        r"\b(previous|prior|system|developer|hidden)\b.{0,70}"
        r"\b(instructions?|rules?|policy|prompt)\b.{0,70}"
        r"\b(ignore(?:d)?|disregard(?:ed)?|override(?:n)?|bypass(?:ed)?)\b"
    ),
    re.compile(
        r"\b(bo qua|boqua|phot lo|photlo|quen|ghi de|ghide|vo hieu hoa|vohieuhoa)\b.{0,90}"
        r"\b(huong dan|huongdan|chi thi|chithi|quy tac|quytac|chinh sach|chinhsach|he thong|hethong|truoc)\b"
    ),
)
_PROMPT_EXTRACTION = re.compile(
    r"\b(show|reveal|print|dump|display|expose|leak|hien thi|hienthi|tiet lo|tietlo|in ra|cho xem)\b.{0,100}"
    r"\b(system prompt|developer message|hidden instructions?|internal policy|prompt he thong|prompthethong|"
    r"chi thi noi bo|chithinoibo|huong dan an|huongdan an)\b"
)
_BENIGN_PROMPT_SAFETY_DISCUSSION = re.compile(
    r"\b(?:should not|must not|do not|khong nen|khong duoc)\b.{0,40}"
    r"\b(?:show|reveal|display|expose|hien thi|tiet lo)\b.{0,80}"
    r"\b(?:system prompt|developer message|hidden instruction|internal policy|prompt he thong)\b"
)
_RBAC_ESCALATION = (
    re.compile(
        r"\b(pretend|act as|treat me as|set my role|switch my role|grant me|make me|i am)\b.{0,70}"
        r"\b(admin|administrator|security admin|data owner|restricted reader|manager)\b"
    ),
    re.compile(
        r"\b(coi toi la|toi la|gan quyen|doi vai tro|nang quyen|cap quyen)\b.{0,70}"
        r"\b(admin|quan tri|bao mat|data owner|restricted|manager)\b"
    ),
    re.compile(
        r"\b(bypass|disable|ignore|bo qua|vo hieu hoa)\b.{0,70}\b(rbac|acl|authorization|access control|phan quyen)\b"
    ),
)
_SECRET_EXFILTRATION = (
    re.compile(
        r"\b(show|reveal|print|dump|display|expose|leak|steal|hien thi|tiet lo|in ra|lay cap|danh cap)\b.{0,100}"
        r"\b(api[ _-]?keys?|access tokens?|secrets?|passwords?|credentials?|environment variables?|"
        r"bien moi truong|mat khau|khoa api)\b"
    ),
    re.compile(
        r"\b(send|upload|post|forward|exfiltrate|gui|tai len|chuyen)\b.{0,120}"
        r"\b(context|documents?|data|secrets?|tokens?|du lieu|tai lieu)\b.{0,120}"
        r"\b(https?|url|webhook|email|server|endpoint)\b"
    ),
)
_TOOL_ABUSE = re.compile(
    r"\b(execute|run|launch|call|invoke|thuc thi|chay|goi)\b.{0,70}"
    r"\b(shell|powershell|bash|cmd|curl|wget|python|tool|function|command|lenh)\b"
)
_ROLE_MARKER = re.compile(
    r"(?:(^|\n)\s*(system|developer|assistant)\s*[:>]"
    r"|<\|?(?:system|developer|assistant|im_start)[^>]*\|?>"
    r"|\[(?:system|developer|assistant|inst)\])",
    re.MULTILINE,
)
_JAILBREAK = (
    re.compile(
        r"\b(you are now|act as|roleplay as|enter|enable)\b.{0,80}"
        r"\b(dan|developer mode|jailbreak|unrestricted|uncensored|without restrictions)\b"
    ),
    re.compile(r"\b(do anything now|developer mode|jailbreak mode|unrestricted mode)\b"),
    re.compile(
        r"\b(dong vai|bat che do|chuyen sang che do)\b.{0,80}"
        r"\b(khong kiem duyet|khong gioi han|developer|jailbreak)\b"
    ),
)
_INDIRECT_TARGET = re.compile(
    r"\b(assistant|model|chatgpt|llm|agent|tro ly|troly|mo hinh|mohinh|he thong|hethong)\b.{0,90}"
    r"\b(must|should|ignore|override|execute|send|reveal|phai|hay|bo qua|ghi de|thuc thi|gui|tiet lo)\b"
)

_SECRET_OUTPUT = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b", re.IGNORECASE),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}=*", re.IGNORECASE),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\s*\.\s*[A-Za-z0-9_-]{10,}\s*\.\s*[A-Za-z0-9_-]{10,}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:api[_ -]?key|access[_ -]?token|secret|password|mat khau|khoa api)\s*[:=]\s*[\"']?[^\s\"']{8,}",
        re.IGNORECASE,
    ),
)
_PII_OUTPUT = re.compile(
    r"(?:"
    r"\b(?:cccd|cmnd|citizen id|passport|so dien thoai|phone|email|ma dinh danh)\s*[:=]?\s*\S+"
    r"|\b[A-Z0-9._%+-]+\s*@\s*[A-Z0-9.-]+\s*\.\s*[A-Z]{2,}\b"
    r"|(?<!\d)(?:\+?84|0)(?:[ .-]?\d){9,10}(?!\d)"
    r")",
    re.IGNORECASE,
)
_PII_ID_CONTEXT = re.compile(
    r"\b(?:cccd|cmnd|citizen id|passport|ma dinh danh)\b.{0,40}\b[a-z]?\d{8,12}\b"
)
_SEMANTIC_ATTACK = (
    re.compile(
        r"\b(always|regardless|whatever|bat ke|du the nao|luon)\b.{0,100}"
        r"\b(answer|respond|return|output|emit|tra loi|phan hoi|ket luan)\b.{0,100}"
        r"\b(approved|allowed|valid|yes|cho phep|hop le|dong y)\b"
    ),
    re.compile(
        r"\b(evidence|document|passage|retrieved text|bang chung|tai lieu|doan van)\b.{0,100}"
        r"\b(highest priority|authoritative|takes precedence|uu tien cao nhat|co tham quyen)\b"
    ),
    re.compile(
        r"\b(without|skip|avoid|khong can|bo qua)\b.{0,80}"
        r"\b(checking|validating|verification|kiem tra|xac minh)\b.{0,80}"
        r"\b(permissions?|authorization|sources?|evidence|quyen|nguon|bang chung)\b"
    ),
)
_PROMPT_LEAK_OUTPUT = re.compile(
    r"\b(?:system prompt|developer message|hidden instructions?|internal policy|prompt he thong|chi thi noi bo)\s*[:=]",
    re.IGNORECASE,
)

_RISK_BY_REASON = {
    GuardrailReason.DIRECT_PROMPT_INJECTION: 0.98,
    GuardrailReason.JAILBREAK_OR_PERSONA_OVERRIDE: 0.98,
    GuardrailReason.ENCODED_PROMPT_INJECTION: 1.0,
    GuardrailReason.PROMPT_OR_POLICY_EXTRACTION: 1.0,
    GuardrailReason.RBAC_ESCALATION: 1.0,
    GuardrailReason.SECRET_EXFILTRATION: 1.0,
    GuardrailReason.TOOL_OR_NETWORK_ABUSE: 0.95,
    GuardrailReason.INPUT_TOO_LARGE: 1.0,
    GuardrailReason.EXCESSIVE_INPUT_LINES: 0.9,
    GuardrailReason.EMPTY_AFTER_NORMALIZATION: 1.0,
    GuardrailReason.CONTROL_CHARACTERS_REMOVED: 0.35,
    GuardrailReason.INDIRECT_PROMPT_INJECTION: 1.0,
    GuardrailReason.EVIDENCE_TOO_LARGE: 0.95,
    GuardrailReason.OUTPUT_TOO_LARGE: 1.0,
    GuardrailReason.OUTPUT_EMPTY: 0.9,
    GuardrailReason.OUTPUT_SECRET_LEAK: 1.0,
    GuardrailReason.OUTPUT_PII_LEAK: 1.0,
    GuardrailReason.OUTPUT_PROMPT_LEAK: 1.0,
    GuardrailReason.OUTPUT_UNVERIFIED: 1.0,
}


@dataclass(frozen=True)
class RetrievalInspection:
    decision: GuardrailDecision
    clean_candidates: list[Candidate]
    quarantined_candidates: list[Candidate]


def normalize_untrusted_text(value: str) -> tuple[str, bool]:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _INVISIBLE_OR_BIDI.sub("", normalized)
    cleaned = re.sub(r"[\t\f\v ]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned).strip()
    return cleaned, cleaned != value


def _skeleton(value: str) -> str:
    value, _ = normalize_untrusted_text(value)
    value = value.casefold().translate(_CONFUSABLES)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = _SPACED_LETTERS.sub(lambda match: "".join(match.group(0).split()), value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _decoded_payloads(value: str) -> list[str]:
    decoded: list[str] = []
    for token in _BASE64_TOKEN.findall(value):
        try:
            padded = token.replace("-", "+").replace("_", "/") + "=" * (-len(token) % 4)
            raw = base64.b64decode(padded, validate=True)
            text = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if text and sum(character.isprintable() or character.isspace() for character in text) / len(text) >= 0.9:
            decoded.append(text[:8000])
    for token in _HEX_TOKEN.findall(value):
        try:
            text = bytes.fromhex(token).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        if text:
            decoded.append(text[:8000])
    if len(re.findall(r"%[0-9A-Fa-f]{2}", value)) >= 4:
        decoded.append(unquote(value)[:8000])
    if "rot13" in _skeleton(value):
        decoded.append(codecs.decode(value, "rot_13")[:8000])
    return decoded


def _content_reasons(value: str, *, indirect: bool) -> set[GuardrailReason]:
    skeleton = _skeleton(value)
    reasons: set[GuardrailReason] = set()
    if any(pattern.search(skeleton) for pattern in _DIRECT_INJECTION) or _ROLE_MARKER.search(skeleton):
        reasons.add(GuardrailReason.INDIRECT_PROMPT_INJECTION if indirect else GuardrailReason.DIRECT_PROMPT_INJECTION)
    if any(pattern.search(skeleton) for pattern in _JAILBREAK):
        reasons.add(GuardrailReason.JAILBREAK_OR_PERSONA_OVERRIDE)
    if _PROMPT_EXTRACTION.search(skeleton) and not _BENIGN_PROMPT_SAFETY_DISCUSSION.search(skeleton):
        reasons.add(GuardrailReason.PROMPT_OR_POLICY_EXTRACTION)
    if any(pattern.search(skeleton) for pattern in _RBAC_ESCALATION):
        reasons.add(GuardrailReason.RBAC_ESCALATION)
    if any(pattern.search(skeleton) for pattern in _SECRET_EXFILTRATION):
        reasons.add(GuardrailReason.SECRET_EXFILTRATION)
    if _TOOL_ABUSE.search(skeleton):
        reasons.add(GuardrailReason.TOOL_OR_NETWORK_ABUSE)
    if indirect and _INDIRECT_TARGET.search(skeleton):
        reasons.add(GuardrailReason.INDIRECT_PROMPT_INJECTION)
    if any(pattern.search(skeleton) for pattern in _SEMANTIC_ATTACK):
        reasons.add(
            GuardrailReason.INDIRECT_PROMPT_INJECTION
            if indirect
            else GuardrailReason.DIRECT_PROMPT_INJECTION
        )

    decoded_reasons: set[GuardrailReason] = set()
    for decoded in _decoded_payloads(value):
        decoded_reasons.update(_content_reasons_without_decoding(decoded, indirect=indirect))
    if decoded_reasons:
        reasons.update(decoded_reasons)
        reasons.add(GuardrailReason.ENCODED_PROMPT_INJECTION)
    return reasons


def _content_reasons_without_decoding(value: str, *, indirect: bool) -> set[GuardrailReason]:
    skeleton = _skeleton(value)
    reasons: set[GuardrailReason] = set()
    if any(pattern.search(skeleton) for pattern in _DIRECT_INJECTION) or _ROLE_MARKER.search(skeleton):
        reasons.add(GuardrailReason.INDIRECT_PROMPT_INJECTION if indirect else GuardrailReason.DIRECT_PROMPT_INJECTION)
    if any(pattern.search(skeleton) for pattern in _JAILBREAK):
        reasons.add(GuardrailReason.JAILBREAK_OR_PERSONA_OVERRIDE)
    if _PROMPT_EXTRACTION.search(skeleton) and not _BENIGN_PROMPT_SAFETY_DISCUSSION.search(skeleton):
        reasons.add(GuardrailReason.PROMPT_OR_POLICY_EXTRACTION)
    if any(pattern.search(skeleton) for pattern in _RBAC_ESCALATION):
        reasons.add(GuardrailReason.RBAC_ESCALATION)
    if any(pattern.search(skeleton) for pattern in _SECRET_EXFILTRATION):
        reasons.add(GuardrailReason.SECRET_EXFILTRATION)
    if _TOOL_ABUSE.search(skeleton):
        reasons.add(GuardrailReason.TOOL_OR_NETWORK_ABUSE)
    if indirect and _INDIRECT_TARGET.search(skeleton):
        reasons.add(GuardrailReason.INDIRECT_PROMPT_INJECTION)
    if any(pattern.search(skeleton) for pattern in _SEMANTIC_ATTACK):
        reasons.add(
            GuardrailReason.INDIRECT_PROMPT_INJECTION
            if indirect
            else GuardrailReason.DIRECT_PROMPT_INJECTION
        )
    return reasons


def _decision(
    stage: GuardrailStage,
    reasons: Iterable[GuardrailReason],
    *,
    policy_version: str,
    sanitized: bool = False,
) -> GuardrailDecision:
    unique = sorted(set(reasons), key=lambda item: item.value)
    blocking = [reason for reason in unique if reason is not GuardrailReason.CONTROL_CHARACTERS_REMOVED]
    if blocking:
        action = GuardrailAction.BLOCK
    elif sanitized:
        action = GuardrailAction.SANITIZE
    else:
        action = GuardrailAction.ALLOW
    risk = max((_RISK_BY_REASON[reason] for reason in unique), default=0.0)
    return GuardrailDecision(
        action=action,
        stage=stage,
        reason_codes=unique,
        risk_score=risk,
        policy_version=policy_version,
    )


def inspect_input(
    value: str,
    *,
    policy_version: str,
    max_chars: int,
    max_lines: int,
) -> TextInspection:
    normalized, changed = normalize_untrusted_text(value)
    reasons = _content_reasons(normalized, indirect=False)
    if len(value) > max_chars:
        reasons.add(GuardrailReason.INPUT_TOO_LARGE)
    if value.count("\n") + 1 > max_lines:
        reasons.add(GuardrailReason.EXCESSIVE_INPUT_LINES)
    if not normalized:
        reasons.add(GuardrailReason.EMPTY_AFTER_NORMALIZATION)
    if changed:
        reasons.add(GuardrailReason.CONTROL_CHARACTERS_REMOVED)
    return TextInspection(
        normalized_text=normalized,
        decision=_decision(
            GuardrailStage.INPUT,
            reasons,
            policy_version=policy_version,
            sanitized=changed,
        ),
    )


def _nested_strings(value: Any, *, max_depth: int = 8) -> Iterable[str]:
    """Yield strings from bounded nested response/metadata structures."""

    if max_depth < 0:
        return
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from _nested_strings(item, max_depth=max_depth - 1)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _nested_strings(item, max_depth=max_depth - 1)
        return
    if hasattr(value, "model_dump"):
        yield from _nested_strings(value.model_dump(mode="json"), max_depth=max_depth - 1)


def inspect_retrieved_candidates_detailed(
    candidates: Sequence[Candidate],
    *,
    policy_version: str,
    max_chars_per_candidate: int,
) -> RetrievalInspection:
    reasons: set[GuardrailReason] = set()
    clean: list[Candidate] = []
    quarantined: list[Candidate] = []
    for candidate in candidates:
        candidate_reasons: set[GuardrailReason] = set()
        if len(candidate.content) > max_chars_per_candidate:
            candidate_reasons.add(GuardrailReason.EVIDENCE_TOO_LARGE)
        texts = [candidate.content[:max_chars_per_candidate], *_nested_strings(candidate.metadata)]
        for text in texts:
            detected = _content_reasons(text, indirect=True)
            if detected:
                detected.discard(GuardrailReason.DIRECT_PROMPT_INJECTION)
                detected.add(GuardrailReason.INDIRECT_PROMPT_INJECTION)
                candidate_reasons.update(detected)
        if candidate_reasons:
            quarantined.append(candidate)
            reasons.update(candidate_reasons)
        else:
            clean.append(candidate)
    decision = _decision(
        GuardrailStage.RETRIEVAL,
        reasons,
        policy_version=policy_version,
    )
    if quarantined and clean:
        decision = decision.model_copy(update={"action": GuardrailAction.SANITIZE})
    return RetrievalInspection(
        decision=decision,
        clean_candidates=clean,
        quarantined_candidates=quarantined,
    )


def inspect_retrieved_candidates(
    candidates: Sequence[Candidate],
    *,
    policy_version: str,
    max_chars_per_candidate: int,
) -> GuardrailDecision:
    return inspect_retrieved_candidates_detailed(
        candidates,
        policy_version=policy_version,
        max_chars_per_candidate=max_chars_per_candidate,
    ).decision


def inspect_output(
    answer: str,
    *,
    warnings: Sequence[str] = (),
    citations: Sequence[Any] = (),
    messages: Sequence[str] = (),
    citation_count: int,
    had_evidence: bool,
    policy_version: str,
    max_chars: int,
    block_pii: bool,
) -> GuardrailDecision:
    reasons: set[GuardrailReason] = set()
    if not answer.strip():
        reasons.add(GuardrailReason.OUTPUT_EMPTY)
    if len(answer) > max_chars:
        reasons.add(GuardrailReason.OUTPUT_TOO_LARGE)
    response_strings = [
        answer,
        *_nested_strings(warnings),
        *_nested_strings(citations),
        *_nested_strings(messages),
    ]
    for value in response_strings:
        normalized_value, _ = normalize_untrusted_text(value)
        if any(pattern.search(normalized_value) for pattern in _SECRET_OUTPUT):
            reasons.add(GuardrailReason.OUTPUT_SECRET_LEAK)
        if block_pii and (
            _PII_OUTPUT.search(normalized_value)
            or _PII_ID_CONTEXT.search(_skeleton(value))
        ):
            reasons.add(GuardrailReason.OUTPUT_PII_LEAK)
        if _PROMPT_LEAK_OUTPUT.search(normalized_value):
            reasons.add(GuardrailReason.OUTPUT_PROMPT_LEAK)
    if had_evidence and citation_count == 0:
        reasons.add(GuardrailReason.OUTPUT_UNVERIFIED)
    return _decision(
        GuardrailStage.OUTPUT,
        reasons,
        policy_version=policy_version,
    )


__all__ = [
    "inspect_input",
    "inspect_output",
    "inspect_retrieved_candidates",
    "inspect_retrieved_candidates_detailed",
    "normalize_untrusted_text",
]
