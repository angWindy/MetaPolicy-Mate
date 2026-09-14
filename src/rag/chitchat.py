"""Deterministic responses for small talk and assistant information.

The chitchat node short-circuits the retrieval workflow so a greeting
never pays the cost of a Qdrant query. Confidence is reported as
"high" because the response is template-driven and has no hallucinated
content.

Templates are sourced from ``CHITCHAT_TEMPLATES`` below. The greeting
template includes the tenant display name so multi-tenant deployments
do not leak the HUST/HUCE default branding. ``resolve_chitchat_templates``
injects the configured tenant name at workflow startup.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.rag.workflow import RetrievalState

# Default templates use the placeholder ``{tenant_name}`` which is
# substituted at runtime with ``RAGSettings.tenant_display_name``. The
# default value below mirrors the production default so single-tenant
# demos continue to work without any configuration.
CHITCHAT_TEMPLATES: dict[str, str] = {
    "greeting": (
        "Xin chào! Tôi là trợ lý tra cứu quy định của {tenant_name}. "
        "Bạn có câu hỏi nào về quy chế, quy định không?"
    ),
    "thanks": (
        "Không có gì! Nếu cần tra cứu thêm, bạn cứ hỏi nhé."
    ),
    "farewell": (
        "Tạm biệt! Chúc bạn một ngày tốt lành."
    ),
    "self_introduction": (
        "Tôi là trợ lý AI P-234 PolicyMeta của {tenant_name}. "
        "Tôi hỗ trợ tra cứu quy chế, quy định và thông tin nghiệp vụ "
        "trong kho tài liệu được hệ thống cho phép truy cập."
    ),
    "help": (
        "Tôi có thể giúp bạn tìm tài liệu, tra cứu quy chế và quy định, "
        "trả lời dựa trên nội dung nguồn và cung cấp trích dẫn để kiểm chứng. "
        "Bạn hãy nêu nội dung, số hiệu văn bản hoặc vấn đề cần tra cứu."
    ),
}

# Mapping from school_code (department.code in JWT) to the display name
# used in chitchat + system prompt. Multi-tenant deployments override
# this via the ``TENANT_DISPLAY_NAMES`` env var (comma-separated
# ``CODE=Display Name`` pairs, e.g. ``HUST=Foo,HUCE=Bar``).
#
# IMPORTANT: this is the ONLY place in the codebase where the human-
# readable school name lives for the LLM prompt. Adding a new school
# means adding one line below.
DEFAULT_TENANT_DISPLAY_NAMES: dict[str, str] = {
    "HUST": "Hanoi University of Science and Technology (HUST)",
    "HUCE": "Hanoi University of Civil Engineering (HUCE)",
}

# Display name used for users who have no school binding (admin / platform
# operators) or whose school is not in the mapping. Generic on purpose:
# admins typically work across schools and must not be misled into thinking
# the LLM is bound to a single school.
GENERAL_TENANT_DISPLAY_NAME = "P-234 PolicyMeta"


def resolve_tenant_display_name(
    school_code: str,
    roles: set[str] | None = None,
    overrides: dict[str, str] | None = None,
) -> str:
    """Resolve the human-readable tenant name for the LLM prompt.

    Resolution order:
    1. ``overrides`` dict (operator-supplied via ``TENANT_DISPLAY_NAMES``).
    2. ``DEFAULT_TENANT_DISPLAY_NAMES`` (built-in mapping).
    3. ``GENERAL_TENANT_DISPLAY_NAME`` (fallback for admin / unknown).

    Admin users (role contains ``admin``) ALWAYS get the general display
    name — they govern all schools, so the LLM must answer generically
    rather than impersonating a specific institution.

    Args:
        school_code: Department code from JWT (e.g. ``HUST``, ``HUCE``,
            ``""`` for users with no school binding).
        roles: Set of role codes (lower-cased). When ``admin`` is
            present, the general display name is returned regardless of
            ``school_code``.
        overrides: Optional dict mapping school_code → display name
            (typically loaded from ``TENANT_DISPLAY_NAMES`` env var).

    Returns:
        Human-readable tenant name safe to substitute into LLM prompts.
    """
    role_set = {role.strip().lower() for role in (roles or set()) if role.strip()}
    if "admin" in role_set:
        return GENERAL_TENANT_DISPLAY_NAME
    code = (school_code or "").strip().upper()
    if not code:
        return GENERAL_TENANT_DISPLAY_NAME
    # Operator overrides (env-supplied) take precedence over built-in
    # defaults so deployments can rebrand schools without code changes.
    candidates = {**DEFAULT_TENANT_DISPLAY_NAMES, **(overrides or {})}
    if code in candidates:
        return candidates[code]
    return GENERAL_TENANT_DISPLAY_NAME

_THANKS_RE = re.compile(
    r"(cảm ơn|cám ơn|thank you|thanks|thank)", flags=re.IGNORECASE
)
_FAREWELL_RE = re.compile(
    r"(tạm biệt|bye|goodbye|see you|chào tạm biệt)", flags=re.IGNORECASE
)
_SELF_INTRODUCTION_RE = re.compile(
    r"(bạn\s+là\s+ai|bạn\s+tên(?:\s+là)?\s+gì|giới\s+thiệu|tự\s+giới\s+thiệu)",
    flags=re.IGNORECASE,
)
_HELP_RE = re.compile(
    r"(có\s+thể\s+làm|hỗ\s+trợ|tác\s+dụng|chức\s+năng|khả\s+năng|"
    r"có\s+thể\s+hỏi|hướng\s+dẫn.*sử\s+dụng)",
    flags=re.IGNORECASE,
)


def _detect_kind(query: str) -> str:
    if _SELF_INTRODUCTION_RE.search(query):
        return "self_introduction"
    if _HELP_RE.search(query):
        return "help"
    if _THANKS_RE.search(query):
        return "thanks"
    if _FAREWELL_RE.search(query):
        return "farewell"
    return "greeting"


def resolve_chitchat_templates(
    tenant_display_name: str | None = None,
    *,
    school_code: str = "",
    roles: set[str] | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Materialize chitchat templates with the configured tenant name.

    Two calling conventions are supported:

    1. Pass ``tenant_display_name`` directly (the resolved string).
    2. Pass ``school_code`` + ``roles``; the tenant display name is
       resolved via :func:`resolve_tenant_display_name` (this is the
       per-user path used by the chat workflow).

    Returns a fresh dict so the caller can mutate it without affecting
    subsequent resolutions.
    """
    if tenant_display_name is None:
        tenant_display_name = resolve_tenant_display_name(
            school_code, roles, overrides
        )
    return {
        kind: template.format(tenant_name=tenant_display_name)
        for kind, template in CHITCHAT_TEMPLATES.items()
    }


async def chitchat_response_node(state: RetrievalState) -> dict[str, Any]:
    """Return a deterministic small-talk answer and skip retrieval.

    Declared ``async`` so ``RetrievalWorkflow._instrument_node`` can
    ``await`` the node uniformly across the graph (the langgraph
    contract requires every node to be awaitable). The body itself is
    synchronous; the ``async def`` is purely structural.
    """

    # Lazy import to avoid a circular dependency with ``workflow``.
    from src.rag.workflow import _visit

    original = (state.get("original_query") or state.get("query") or "").strip()
    kind = _detect_kind(original)
    templates = state.get("chitchat_templates") or CHITCHAT_TEMPLATES
    answer = templates[kind]
    return {
        "answer": answer,
        "citations": [],
        "cited_chunk_ids": [],
        "warnings": [],
        "confidence": "high",
        "outcome": "chitchat_response",
        "visited": _visit(state, "chitchat_response_node"),
    }


__all__ = [
    "CHITCHAT_TEMPLATES",
    "DEFAULT_TENANT_DISPLAY_NAMES",
    "GENERAL_TENANT_DISPLAY_NAME",
    "chitchat_response_node",
    "resolve_chitchat_templates",
    "resolve_tenant_display_name",
]
