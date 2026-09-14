"""Deterministic, offline quality observations for the MVP regression corpus.

This evaluator is intentionally labelled local/deterministic.  It does not
claim to be an LLM-as-judge RAGAS run and therefore cannot silently satisfy a
gate that explicitly requires an external RAGAS judge.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.findall(r"[\w]+", normalized, flags=re.UNICODE)


def token_f1(reference: str, answer: str) -> float:
    reference_tokens = _tokens(reference)
    answer_tokens = _tokens(answer)
    if not reference_tokens or not answer_tokens:
        return 0.0
    reference_counts = {token: reference_tokens.count(token) for token in set(reference_tokens)}
    answer_counts = {token: answer_tokens.count(token) for token in set(answer_tokens)}
    overlap = sum(
        min(count, answer_counts.get(token, 0))
        for token, count in reference_counts.items()
    )
    precision = overlap / len(answer_tokens)
    recall = overlap / len(reference_tokens)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def average_precision(actual: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    hits = 0
    total = 0.0
    for rank, item in enumerate(actual, start=1):
        if item in expected:
            hits += 1
            total += hits / rank
    return total / len(expected)


def context_recall(actual: Sequence[str], expected: set[str]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    return len(set(actual).intersection(expected)) / len(expected)


def extractive_faithfulness(answer: str, evidence_texts: Sequence[str]) -> float:
    """Score 1 only when a complete evidence span is present in the answer."""

    answer_tokens = _tokens(answer)
    if not answer_tokens:
        return 0.0
    normalized_answer = " ".join(answer_tokens)
    return float(
        any(
            " ".join(_tokens(text)) in normalized_answer
            for text in evidence_texts
            if _tokens(text)
        )
    )


__all__ = [
    "average_precision",
    "context_recall",
    "extractive_faithfulness",
    "token_f1",
]
