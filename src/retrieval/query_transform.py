from __future__ import annotations

import re
import unicodedata

from src.domain.schemas import QueryType

MAX_QUERY_LENGTH = 5000

DOCUMENT_NUMBER_PATTERN = re.compile(
    r"(?<![\w/-])\d{1,6}/[A-ZÀ-ỸĐ0-9]+(?:-[A-ZÀ-ỸĐ0-9]+)+(?![\w-])",
    flags=re.IGNORECASE,
)
FORM_CODE_PATTERN = re.compile(
    r"(?<![\w/])(?:[A-ZÀ-ỸĐ]{2,}-)+(?:[A-ZÀ-ỸĐ]*\d+[A-ZÀ-ỸĐ0-9]*)(?![\w-])",
    flags=re.IGNORECASE,
)
BARE_DOCUMENT_REFERENCE_PATTERN = re.compile(
    r"\b(?:qđ|qd|quy\s+định|quy\s+dinh|quy\s+chế|quy\s+che|"
    r"quyết\s+định|quyet\s+dinh)(?:\s+[^\d\W_]+){0,2}\s*(?:số|so)?\s*(\d{2,6})\b(?!\s*/)",
    flags=re.IGNORECASE,
)
ALPHANUMERIC_IDENTIFIER_PATTERN = re.compile(
    r"(?<![\w/-])(?=[A-Z0-9]{6,24}(?![\w-]))"
    r"(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+(?![\w-])",
    flags=re.IGNORECASE,
)
ARTICLE_PATTERN = re.compile(r"\b(?:điều|dieu)\s+(\d+[a-zđ]?)\b", flags=re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"\b(?:khoản|khoan)\s+(\d+[a-zđ]?)\b", flags=re.IGNORECASE)
QUESTION_CUE_PATTERN = re.compile(
    r"\b(?:ai|gì|gi|nào|nao|khi nào|khi nao|ở đâu|o dau|tại sao|tai sao|"
    r"thế nào|the nao|bao nhiêu|bao nhieu|được không|duoc khong|làm sao|lam sao)\b",
    flags=re.IGNORECASE,
)
MULTI_INTENT_CONNECTOR_PATTERN = re.compile(
    r"\b(?:và|va|đồng thời|dong thoi|ngoài ra|ngoai ra)\b",
    flags=re.IGNORECASE,
)


def normalize_unicode(query: str) -> str:
    return unicodedata.normalize("NFC", query)


def normalize_whitespace(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _unique_matches(pattern: re.Pattern[str], query: str) -> list[str]:
    return list(dict.fromkeys(match.group(0) for match in pattern.finditer(query)))


def extract_document_numbers(query: str) -> list[str]:
    normalized = normalize_unicode(query)
    values = _unique_matches(DOCUMENT_NUMBER_PATTERN, normalized)
    values.extend(
        match.group(1) for match in BARE_DOCUMENT_REFERENCE_PATTERN.finditer(normalized)
    )
    return list(dict.fromkeys(values))


def extract_article_clause(query: str) -> dict[str, list[str]]:
    normalized = normalize_unicode(query)
    return {
        "articles": list(
            dict.fromkeys(match.group(1) for match in ARTICLE_PATTERN.finditer(normalized))
        ),
        "clauses": list(
            dict.fromkeys(match.group(1) for match in CLAUSE_PATTERN.finditer(normalized))
        ),
    }


def extract_form_codes(query: str) -> list[str]:
    return _unique_matches(FORM_CODE_PATTERN, normalize_unicode(query))


def extract_alphanumeric_identifiers(query: str) -> list[str]:
    """Extract opaque IDs such as student code ``20240799E``.

    The token must contain both a letter and a digit. Pure years, ordinary
    words, document numbers, and hyphenated form codes are handled elsewhere.
    """

    return _unique_matches(ALPHANUMERIC_IDENTIFIER_PATTERN, normalize_unicode(query))


def validate_query(query: str, *, max_length: int = MAX_QUERY_LENGTH) -> str:
    if not isinstance(query, str):
        raise TypeError("Query must be a string.")
    if not query.strip():
        raise ValueError("Query must not be empty.")
    if len(query) > max_length:
        raise ValueError(f"Query must not exceed {max_length} characters.")
    if not any(character.isalnum() for character in query):
        raise ValueError("Query must contain at least one letter or number.")
    return query


def _identifier_spans(query: str) -> list[tuple[int, int]]:
    spans = [
        match.span()
        for pattern in (
            DOCUMENT_NUMBER_PATTERN,
            FORM_CODE_PATTERN,
            ALPHANUMERIC_IDENTIFIER_PATTERN,
            ARTICLE_PATTERN,
            CLAUSE_PATTERN,
        )
        for match in pattern.finditer(query)
    ]
    if not spans:
        return []
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _remove_diacritics(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    )
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _accentless_variant_preserving_identifiers(query: str) -> str:
    spans = _identifier_spans(query)
    if not spans:
        return _remove_diacritics(query)
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(_remove_diacritics(query[cursor:start]))
        parts.append(query[start:end])
        cursor = end
    parts.append(_remove_diacritics(query[cursor:]))
    return "".join(parts)


def _is_multi_intent(query: str) -> bool:
    if len([part for part in re.split(r"\?+", query) if part.strip()]) > 1:
        return True
    if ";" in query and len([part for part in query.split(";") if part.strip()]) > 1:
        return True
    question_cues = QUESTION_CUE_PATTERN.findall(query)
    return bool(
        MULTI_INTENT_CONNECTOR_PATTERN.search(query) and len(question_cues) >= 2
    )


def classify_query_type(query: str) -> QueryType:
    validate_query(query)
    normalized = normalize_whitespace(normalize_unicode(query))
    if _is_multi_intent(normalized):
        return QueryType.MULTI_INTENT

    spans = _identifier_spans(normalized)
    if spans:
        remainder = list(normalized)
        for start, end in spans:
            remainder[start:end] = " " * (end - start)
        if not any(character.isalnum() for character in remainder):
            return QueryType.IDENTIFIER
        return QueryType.MIXED

    tokens = re.findall(r"\w+", normalized, flags=re.UNICODE)
    if QUESTION_CUE_PATTERN.search(normalized) or len(tokens) >= 6:
        return QueryType.SEMANTIC
    return QueryType.KEYWORD


def build_query_variants(query: str) -> list[str]:
    original = validate_query(query)
    normalized = normalize_whitespace(normalize_unicode(original))
    accentless = _accentless_variant_preserving_identifiers(normalized)

    variants: list[str] = []
    for variant in (original, normalized, accentless):
        if variant and variant not in variants:
            variants.append(variant)
    return variants[:3]
