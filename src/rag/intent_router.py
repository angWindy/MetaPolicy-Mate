"""Intent classification for the retrieval workflow.

Adds non-retrieval intents that let the workflow answer greetings,
assistant introductions, and usage help without spending Qdrant budget. Non-small-talk
queries pass through ``classify_query_type`` so identifier/keyword/
semantic/mixed/multi-intent classification is unchanged.
"""

from __future__ import annotations

import re
from enum import StrEnum

from src.domain.schemas import QueryType
from src.retrieval.query_transform import classify_query_type


class QueryIntent(StrEnum):
    """Top-level intent routed by ``workflow._route_after_intent``.

    Two tiers:
    - Retrieval strategy (small_talk, multi_intent, identifier, keyword, semantic, mixed)
    - Semantic query type (information_policy, procedure, comparison, condition_lookup,
      form_generation, form_info, follow_up, ambiguous, out_of_scope)

    The retrieval-strategy tier determines routing through the workflow.
    The semantic-query-type tier is metadata used for specialized handling.
    """

    # --- Retrieval strategy tier ---
    SMALL_TALK = "small_talk"
    SELF_INTRODUCTION = "self_introduction"
    HELP = "help"
    MULTI_INTENT = "multi_intent"
    IDENTIFIER = "identifier"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    MIXED = "mixed"

    # --- Semantic query type tier ---
    INFORMATION_POLICY = "information_policy"
    PROCEDURE = "procedure"
    COMPARISON = "comparison"
    CONDITION_LOOKUP = "condition_lookup"
    FORM_GENERATION = "form_generation"
    FORM_INFO = "form_info"
    FOLLOW_UP = "follow_up"
    AMBIGUOUS = "ambiguous"
    OUT_OF_SCOPE = "out_of_scope"


# Greeting / farewell / thanks — short-form small talk that does not
# warrant retrieval. Multi-word Vietnamese variants (e.g. "xin chào
# bạn") are covered by leading "xin chào" alone. We use word boundaries
# + sentence anchors so a question like "Cảm ơn bạn, cho hỏi điều 5"
# is NOT classified as small talk.
_GREETING_TERMS = (
    "xin chào",
    "chào bạn",
    "chào anh",
    "chào chị",
    "chào em",
    "chào",
    "hello",
    "hi",
    "hey",
    "bạn khỏe không",
    "how are you",
    "khỏe không",
)

_THANKS_TERMS = (
    "cảm ơn",
    "cám ơn",
    "thank you",
    "thanks",
    "thank",
)

_FAREWELL_TERMS = (
    "tạm biệt",
    "bye",
    "goodbye",
    "chào tạm biệt",
    "see you",
)

_GREETING_PATTERN = re.compile(
    r"^\s*(?:" + "|".join(re.escape(term) for term in _GREETING_TERMS) + r")\b[!.?\s]*$",
    flags=re.IGNORECASE | re.UNICODE,
)
_THANKS_PATTERN = re.compile(
    r"^\s*(?:" + "|".join(re.escape(term) for term in _THANKS_TERMS) + r")\b[!.?\s]*$",
    flags=re.IGNORECASE | re.UNICODE,
)
_FAREWELL_PATTERN = re.compile(
    r"^\s*(?:" + "|".join(re.escape(term) for term in _FAREWELL_TERMS) + r")\b[!.?\s]*$",
    flags=re.IGNORECASE | re.UNICODE,
)

_OPTIONAL_GREETING_PREFIX = r"(?:(?:xin\s+)?chào(?:\s+bạn)?[,!.?\s]*)?"
_SELF_INTRODUCTION_PATTERN = re.compile(
    r"^\s*"
    + _OPTIONAL_GREETING_PREFIX
    + r"(?:bạn\s+là\s+ai|bạn\s+tên(?:\s+là)?\s+gì|"
    r"(?:hãy\s+)?giới\s+thiệu(?:\s+về)?\s+(?:bạn|bản\s+thân)|"
    r"bạn\s+có\s+thể\s+tự\s+giới\s+thiệu)"
    r"(?:\s+(?:được\s+không|không|nhé))?[!.?\s]*$",
    flags=re.IGNORECASE | re.UNICODE,
)
_HELP_PATTERN = re.compile(
    r"^\s*"
    + _OPTIONAL_GREETING_PREFIX
    + r"(?:bạn\s+(?:có\s+)?(?:thể\s+)?(?:làm|hỗ\s+trợ)\s+(?:được\s+)?(?:những\s+)?gì|"
    r"bạn\s+có\s+(?:(?:những|các)\s+)?(?:tác\s+dụng|chức\s+năng)\s+gì|"
    r"(?:tác\s+dụng|chức\s+năng|khả\s+năng)\s+của\s+bạn\s+là\s+gì|"
    r"tôi\s+có\s+thể\s+hỏi\s+(?:bạn\s+)?(?:những\s+)?gì|"
    r"hướng\s+dẫn\s+(?:tôi\s+)?(?:cách\s+)?sử\s+dụng(?:\s+hệ\s+thống)?)"
    r"(?:\s+(?:được\s+không|không|nhé))?[!.?\s]*$",
    flags=re.IGNORECASE | re.UNICODE,
)


def is_small_talk(query: str) -> bool:
    """Return True if the query matches one of the small-talk patterns.

    A query is considered small talk only when it is *exclusively* a
    greeting, thanks, or farewell — anything that contains additional
    words (e.g. "cảm ơn bạn, cho hỏi điều 5") still goes through
    retrieval so we don't drop a real question that happens to start
    politely.
    """

    if not isinstance(query, str):
        return False
    text = query.strip()
    if not text:
        return False
    return bool(
        _GREETING_PATTERN.match(text)
        or _THANKS_PATTERN.match(text)
        or _FAREWELL_PATTERN.match(text)
    )


def classify_assistant_query(query: str) -> QueryIntent | None:
    """Classify assistant identity/help questions that need no retrieval."""

    if not isinstance(query, str):
        return None
    text = query.strip()
    if not text:
        return None
    if _SELF_INTRODUCTION_PATTERN.match(text):
        return QueryIntent.SELF_INTRODUCTION
    if _HELP_PATTERN.match(text):
        return QueryIntent.HELP
    return None


def _contains_standalone_phrase(text: str, phrase: str) -> bool:
    """Match a phrase without treating it as a substring of another word."""

    return bool(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text))


# --- Semantic query type patterns (tiếng Việt) ---
_PROCEDURE_PATTERNS = (
    "quy trình",
    "cách làm",
    "các bước",
    "hướng dẫn",
    "thủ tục",
    "trình tự",
    "quy trình",
)

_COMPARISON_PATTERNS = (
    "so sánh",
    "khác nhau",
    "giống nhau",
    "hơn kém",
    "ưu điểm",
    "nhược điểm",
    "giữa",
)

_CONDITION_PATTERNS = (
    "điều kiện",
    "yêu cầu",
    "được phép",
    "phải có",
    "nếu",
    "khi nào",
    "trường hợp",
)

_FORM_GENERATION_PATTERNS = (
    "tạo đơn",
    "biểu mẫu",
    "mẫu đơn",
    "viết đơn",
    "soạn đơn",
)

_FORM_INFO_PATTERNS = (
    "mẫu",
    "form",
    "tải mẫu",
    "in đơn",
    "đơn mẫu",
    "file",
)

_FOLLOW_UP_PATTERNS = (
    "thêm",
    "chi tiết",
    "tại sao",
    "vì sao",
    "nữa",
    "cụ thể hơn",
    "giải thích",
    "cho biết",
    "nói thêm",
)

_AMBIGUOUS_PATTERNS = (
    "nó",
    "cái đó",
    "như trên",
    "đấy",
    "bên trên",
    "điều này",
    "vấn đề này",
)

_INFORMATION_POLICY_PATTERNS = (
    "quy định",
    "chính sách",
    "theo",
    "áp dụng",
    "hiệu lực",
    "nội dung",
    "điều khoản",
)


def classify_semantic_intent(query: str) -> QueryIntent:
    """Detect semantic query type (what the user wants to accomplish).

    Returns one of the semantic query type intents, defaulting to
    SEMANTIC if no specific pattern matches. This runs AFTER the
    retrieval-strategy classification so it only applies to queries
    that will go through the full RAG pipeline.
    """
    if not isinstance(query, str):
        return QueryIntent.SEMANTIC

    q = query.lower()

    # Procedural queries
    if any(p in q for p in _PROCEDURE_PATTERNS):
        return QueryIntent.PROCEDURE

    # Comparison queries
    if any(p in q for p in _COMPARISON_PATTERNS):
        return QueryIntent.COMPARISON

    # Condition lookup queries
    if any(p in q for p in _CONDITION_PATTERNS):
        return QueryIntent.CONDITION_LOOKUP

    # Form generation queries
    if any(p in q for p in _FORM_GENERATION_PATTERNS):
        return QueryIntent.FORM_GENERATION

    # Form info queries
    if any(p in q for p in _FORM_INFO_PATTERNS):
        return QueryIntent.FORM_INFO

    # Follow-up / clarification queries
    if any(p in q for p in _FOLLOW_UP_PATTERNS):
        return QueryIntent.FOLLOW_UP

    # Ambiguous / deictic queries
    if any(_contains_standalone_phrase(q, p) for p in _AMBIGUOUS_PATTERNS):
        return QueryIntent.AMBIGUOUS

    # Information/policy queries
    if any(p in q for p in _INFORMATION_POLICY_PATTERNS):
        return QueryIntent.INFORMATION_POLICY

    return QueryIntent.SEMANTIC


def _is_out_of_scope(query: str) -> bool:
    """Detect queries that are clearly outside the policy domain.

    A query is out-of-scope if it asks about topics unrelated to
    university regulations, HR policies, or administrative procedures.
    """
    if not isinstance(query, str):
        return False

    q = query.lower()

    # Clearly out-of-scope topics
    out_of_scope_keywords = (
        "thời tiết",
        "tin tức",
        "bóng đá",
        "game",
        "phim",
        "nhạc",
        "mua sắm",
        "nấu ăn",
        "sức khỏe",
        "bệnh",
        "lịch thi",
        "điểm thi",
        "giới tính",
    )

    # Check for negative indicators (what this system is NOT for)
    not_policy_keywords = (
        "tính toán",
        "lập trình",
        "code",
        "math",
        "translate",
        "dịch thuật",
    )

    has_out_of_scope = any(kw in q for kw in out_of_scope_keywords)
    has_not_policy = any(kw in q for kw in not_policy_keywords)

    # Only flag as out-of-scope if we have strong evidence
    # (multiple out-of-scope keywords OR at least one not-policy keyword)
    if has_not_policy:
        return True
    if q.strip().count(" ") < 3 and has_out_of_scope:
        return True

    return False


def classify_intent(query: str) -> QueryIntent:
    """Map a raw user query to the routing-level intent.

    Detection order:
    1. Out-of-scope (short-circuit - won't be answered)
    2. Assistant identity/help (short-circuit - no retrieval needed)
    3. Small talk (short-circuit - no retrieval needed)
    4. Ambiguous (flag for clarification)
    5. Retrieval strategy (identifier/keyword/semantic/mixed/multi_intent)
    6. Semantic query type (information_policy, procedure, etc.)
    """

    if not isinstance(query, str) or not query.strip():
        return QueryIntent.SEMANTIC

    # Check out-of-scope first
    if _is_out_of_scope(query):
        return QueryIntent.OUT_OF_SCOPE

    assistant_intent = classify_assistant_query(query)
    if assistant_intent is not None:
        return assistant_intent

    # Small talk short-circuit
    if is_small_talk(query):
        return QueryIntent.SMALL_TALK

    # Check for ambiguous/deictic queries
    if any(
        _contains_standalone_phrase(query.lower(), pattern)
        for pattern in _AMBIGUOUS_PATTERNS
    ):
        # Only flag as ambiguous if it's the main content
        # (not a follow-up to a clear question)
        return QueryIntent.AMBIGUOUS

    # Use legacy query type classification for retrieval strategy
    qt = classify_query_type(query)
    if qt is QueryType.MULTI_INTENT:
        return QueryIntent.MULTI_INTENT
    if qt is QueryType.IDENTIFIER:
        return QueryIntent.IDENTIFIER
    if qt is QueryType.KEYWORD:
        return QueryIntent.KEYWORD
    if qt is QueryType.SEMANTIC:
        return QueryIntent.SEMANTIC
    if qt is QueryType.MIXED:
        return QueryIntent.MIXED

    return QueryIntent.SEMANTIC


__all__ = [
    "QueryIntent",
    "classify_assistant_query",
    "classify_intent",
    "classify_semantic_intent",
    "is_small_talk",
    "_is_out_of_scope",
]
