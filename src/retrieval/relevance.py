"""Deterministic lexical relevance features for the no-model fallback path."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from math import log
from typing import Any

from src.retrieval.keyword import tokenize
from src.retrieval.query_transform import (
    extract_alphanumeric_identifiers,
    extract_document_numbers,
    extract_form_codes,
)

NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?", flags=re.UNICODE)

_LEXICAL_STOP_WORDS = {
    "ai", "bao", "bao_nhieu", "co", "cua", "cho", "duoc", "gi", "hay",
    "he", "hoc_phi", "la", "mot", "moi", "muc", "nao", "nghin", "nhieu",
    "nhung", "qd", "quy", "quyet_dinh", "so", "tchp", "theo", "thi",
    "the", "trong", "va", "ve", "voi",
    "chinh", "chương", "chính", "chuẩn", "đào", "đồng", "hệ", "học", "mức",
    "nghìn", "phí", "quyết", "tạo", "tchp", "trình",
    "được", "gì", "không", "là", "mấy", "mỗi", "nào", "những", "số",
    "thế", "theo", "trong", "và", "về", "với",
}
_FUNCTION_WORDS = {
    "ai", "bao", "co", "cua", "cho", "duoc", "gi", "hay", "la", "mot",
    "moi", "nao", "nhieu", "nhung", "qd", "quy", "so", "theo", "thi",
    "the", "trong", "va", "ve", "voi", "được", "gì", "không", "là",
    "mấy", "mỗi", "nào", "những", "số", "thế", "và", "về", "với",
}
_ANSWER_ANCHOR_STOP_WORDS = _LEXICAL_STOP_WORDS | {
    "ban", "can", "căn", "chuong", "chương", "chuan", "chuẩn", "dao",
    "đào", "dai", "đại", "dinh", "định", "doi", "đối", "hoc", "học",
    "ky", "kỳ", "nam", "năm", "nganh", "ngành", "phi", "phí", "quy",
    "tao", "tạo", "tin", "tín", "trinh", "trình", "truong", "trường",
}


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("–", "-").replace("—", "-").replace("÷", "-")
    return re.sub(r"(?<=\d),(?=\d)", ".", value)


def _token_coverage(query: str, content: str) -> float:
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return 0.0
    return len(query_tokens & set(tokenize(content))) / len(query_tokens)


def _scrub_document_context(value: str) -> str:
    scrubbed = value
    for identifier in extract_document_numbers(value):
        scrubbed = re.sub(
            rf"(?<!\w){re.escape(identifier)}(?!\w)",
            " ",
            scrubbed,
            flags=re.IGNORECASE,
        )
    return re.sub(
        r"(?<!\w)([A-Fa-f])\+(?!\w)",
        lambda match: f" grade_{match.group(1).casefold()}_plus ",
        scrubbed,
    )


def _informative_tokens(value: str) -> list[str]:
    return [
        token
        for token in tokenize(_scrub_document_context(value))
        if len(token) >= 2 and token not in _LEXICAL_STOP_WORDS
    ]


def _phrase_tokens(value: str) -> list[str]:
    return [
        token
        for token in tokenize(_scrub_document_context(value))
        if len(token) >= 2 and token not in _FUNCTION_WORDS
    ]


def _best_window_coverage(query: str, content: str, *, window_size: int = 36) -> float:
    """Measure whether query concepts occur together in one local passage.

    Whole-chunk overlap rewards long boilerplate chunks where terms occur far
    apart. A sliding token window instead favors a sentence or serialized table
    row containing the requested subject and its qualifiers together.
    """

    query_tokens = set(_informative_tokens(query))
    content_tokens = _informative_tokens(content)
    if not query_tokens or not content_tokens:
        return 0.0
    if len(content_tokens) <= window_size:
        return len(query_tokens & set(content_tokens)) / len(query_tokens)
    return max(
        len(query_tokens & set(content_tokens[start : start + window_size]))
        / len(query_tokens)
        for start in range(0, len(content_tokens), max(window_size // 4, 1))
    )


def _query_bigram_coverage(query: str, content: str) -> float:
    query_tokens = _phrase_tokens(query)
    if len(query_tokens) < 2:
        return 0.0
    content_tokens = _phrase_tokens(content)
    content_bigrams = set(zip(content_tokens, content_tokens[1:]))
    query_bigrams = set(zip(query_tokens, query_tokens[1:]))
    return len(query_bigrams & content_bigrams) / len(query_bigrams)


def _structural_relevance_bonus(query: str, content: str) -> float:
    """Reward answer-bearing structures and exact short domain anchors."""

    normalized_query = _normalized(query)
    normalized_content = _normalized(content)
    bonus = 0.0

    plus_grades = set(
        re.findall(r"(?<!\w)[a-f]\+(?!\w)", normalized_query)
    )
    if plus_grades:
        bonus += 0.35 if plus_grades.issubset(
            set(re.findall(r"(?<!\w)[a-f]\+(?!\w)", normalized_content))
        ) else -0.25

    requested_programs = set(
        re.findall(r"\bctđt\s+[\w-]+", normalized_query)
    )
    if requested_programs:
        bonus += 0.20 if any(
            program in normalized_content for program in requested_programs
        ) else -0.10

    count_match = re.search(
        r"\b(?:mấy|bao\s+nhiêu)\s+([\w]+)",
        normalized_query,
    )
    if count_match:
        noun = re.escape(count_match.group(1))
        if re.search(
            rf"(?:\d+\s+(?:\w+\s+){{0,2}}{noun}|{noun}\s+(?:\w+\s+){{0,2}}\d+)",
            normalized_content,
        ):
            bonus += 0.25

    if re.search(r"\bbao\s+nhiêu\b", normalized_query) and "nghìn" in normalized_query:
        query_numbers = set(
            NUMBER_RE.findall(_scrub_document_context(normalized_query))
        )
        answer_numbers = [
            float(value.replace(",", "."))
            for value in NUMBER_RE.findall(normalized_content)
            if value not in query_numbers
            and value.replace(",", ".").count(".") <= 1
        ]
        bonus += 0.20 if any(value >= 10 for value in answer_numbers) else -0.15

    yearly_question = bool(
        re.search(r"(?:mỗi|một)\s+năm|/năm", normalized_query)
    )
    if yearly_question:
        yearly_evidence = bool(
            re.search(r"(?:mỗi|một)\s+năm|/năm|đồng\s*/\s*năm", normalized_content)
        )
        bonus += 0.20 if yearly_evidence else -0.10

    if "chính quy" in normalized_query:
        if "đại học chính quy" in normalized_content:
            bonus += 0.30
        if "vừa làm vừa học" in normalized_content:
            bonus -= 0.30

    return bonus


def expects_numeric_answer(query: str) -> bool:
    """Return whether a question explicitly asks for a numeric value."""

    normalized_query = _normalized(query)
    return bool(
        re.search(r"\b(?:bao\s+nhiêu|mấy)\b", normalized_query)
        and re.search(
            r"\b(?:học\s+phí|tín\s+chỉ|tchp|học\s+kỳ|năm|đợt|mức)\b",
            normalized_query,
        )
    )


def contains_requested_numeric_answer(query: str, content: str) -> bool:
    """Detect an answer value rather than numbers copied from the question.

    Document numbers and school years make heading-only chunks appear numeric.
    They are removed before checking for a value that can actually answer the
    question. Tuition tables often declare the unit in a preceding heading, so
    values of at least ten remain valid even when the row only contains ``630``.
    """

    if not expects_numeric_answer(query):
        return True
    normalized_query = _normalized(_scrub_document_context(query))
    normalized_content = _normalized(_scrub_document_context(content))
    query_numbers = set(NUMBER_RE.findall(normalized_query))
    matches = [
        match
        for match in NUMBER_RE.finditer(normalized_content)
        if match.group(0) not in query_numbers
    ]
    if not matches:
        return False

    anchor_tokens = {
        token
        for token in _informative_tokens(normalized_query)
        if not NUMBER_RE.fullmatch(token)
        and token not in _ANSWER_ANCHOR_STOP_WORDS
    }
    required_anchor_count = min(2, len(anchor_tokens))
    if required_anchor_count:
        matches = [
            match
            for match in matches
            if len(
                anchor_tokens
                & set(
                    _informative_tokens(
                        normalized_content[
                            max(0, match.start() - 220) : match.end() + 220
                        ]
                    )
                )
            )
            >= required_anchor_count
        ]
        if not matches:
            return False

    yearly_question = bool(
        re.search(r"(?:mỗi|một)\s+năm|/năm", normalized_query)
    )
    if yearly_question:
        matches = [
            match
            for match in matches
            if re.search(
                r"(?:mỗi|một|trong|hàng)\s+năm|/\s*năm|đồng\s*/\s*năm",
                normalized_content[
                    max(0, match.start() - 100) : match.end() + 100
                ],
            )
        ]
        if not matches:
            return False

    if re.search(r"\b(?:học\s+phí|tchp|nghìn|triệu|đồng)\b", normalized_query):
        for match in matches:
            value = float(match.group(0).replace(",", "."))
            nearby = normalized_content[
                match.start() : min(len(normalized_content), match.end() + 24)
            ]
            if value >= 10 or re.search(r"\b(?:nghìn|triệu|đồng)\b", nearby):
                return True
        return False
    return True


def lexical_relevance_score(
    query: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> float:
    """Score content with identifier, number, and table-row aware features."""
    metadata = metadata or {}
    metadata_text = " ".join(
        str(metadata.get(key) or "")
        for key in ("document_number", "title", "section", "heading")
    )
    searchable = f"{metadata_text}\n{content}".strip()
    normalized_query = _normalized(query)
    normalized_content = _normalized(searchable)

    coverage = _token_coverage(
        " ".join(_informative_tokens(normalized_query)),
        " ".join(_informative_tokens(normalized_content)),
    )
    window_coverage = _best_window_coverage(normalized_query, normalized_content)
    bigram_coverage = _query_bigram_coverage(normalized_query, normalized_content)
    identifiers = [
        *extract_document_numbers(query),
        *extract_form_codes(query),
        *extract_alphanumeric_identifiers(query),
    ]
    identifier_score = (
        sum(_normalized(item) in normalized_content for item in identifiers)
        / len(identifiers)
        if identifiers
        else 0.0
    )
    query_numbers = set(NUMBER_RE.findall(_scrub_document_context(normalized_query)))
    content_numbers = set(NUMBER_RE.findall(normalized_content))
    number_score = (
        len(query_numbers & content_numbers) / len(query_numbers)
        if query_numbers
        else 0.0
    )

    score = (
        0.25 * coverage
        + 0.40 * window_coverage
        + 0.15 * bigram_coverage
        + 0.15 * identifier_score
        + 0.05 * number_score
        + _structural_relevance_bonus(normalized_query, normalized_content)
    )
    return min(max(score, 0.0), 1.0)


def corpus_lexical_relevance_scores(
    query: str,
    contents: list[str],
    metadata: list[dict[str, Any]] | None = None,
) -> list[float]:
    """Add corpus-relative phrase discrimination to single-chunk scores.

    A phrase appearing in only one candidate (for example ``CTĐT chuẩn`` or
    ``học phần tốt nghiệp``) carries more ranking information than phrases
    repeated in every heading. This is deterministic IDF over the already
    access-filtered candidate pool; it does not alter authorization scope.
    """

    if not contents:
        return []
    metadata = metadata or [{} for _ in contents]
    query_tokens = _phrase_tokens(query)
    query_ngrams = {
        (size, tuple(query_tokens[start : start + size]))
        for size in range(2, min(4, len(query_tokens)) + 1)
        for start in range(len(query_tokens) - size + 1)
    }
    candidate_ngrams = [
        {
            (size, tuple(tokens[start : start + size]))
            for size in range(2, min(4, len(tokens)) + 1)
            for start in range(len(tokens) - size + 1)
        }
        for content in contents
        for tokens in [_phrase_tokens(content)]
    ]
    document_frequency = Counter(
        ngram for ngrams in candidate_ngrams for ngram in ngrams
    )
    phrase_strengths = [
        sum(
            size
            * (1.0 + log((len(contents) + 1) / (document_frequency[ngram] + 1)))
            for ngram in query_ngrams & ngrams
            for size in [ngram[0]]
        )
        for ngrams in candidate_ngrams
    ]
    maximum_strength = max(phrase_strengths, default=0.0)
    base_scores = [
        lexical_relevance_score(query, content, item_metadata)
        for content, item_metadata in zip(contents, metadata, strict=True)
    ]
    if maximum_strength <= 0:
        return base_scores
    return [
        min(0.60 * base + 0.40 * (strength / maximum_strength), 1.0)
        for base, strength in zip(base_scores, phrase_strengths, strict=True)
    ]
