"""Deterministic post-generation checks for factual numeric grounding."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.retrieval.query_transform import (
    extract_alphanumeric_identifiers,
    extract_document_numbers,
)

CITATION_MARKER_RE = re.compile(r"\[\d+(?:\]\[\d+)*\]")
LIST_NUMBER_RE = re.compile(r"(?m)^\s*\d+[.)]\s+")
NUMBER_RE = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)")
GRADE_RE = re.compile(r"(?<!\w)[A-F][+-]?(?!\w)", flags=re.IGNORECASE)


@dataclass(frozen=True)
class GroundingCheck:
    supported: bool
    unsupported_claims: tuple[str, ...] = ()


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.replace("–", "-").replace("—", "-").replace("÷", "-")
    return re.sub(r"\s+", " ", value).strip()


def _canonical_number(value: str) -> str:
    value = value.replace(",", ".")
    parts = value.split(".")
    if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3):
        return "".join(parts)
    return value


def _numbers(value: str) -> set[str]:
    scrubbed = CITATION_MARKER_RE.sub("", LIST_NUMBER_RE.sub("", value))
    for document_number in extract_document_numbers(scrubbed):
        scrubbed = scrubbed.replace(document_number, " ")
    return {_canonical_number(item) for item in NUMBER_RE.findall(scrubbed)}


def _citation_fields(citation: Any) -> dict[str, Any]:
    if hasattr(citation, "model_dump"):
        return citation.model_dump()
    return dict(citation)


def _number_supported(
    claim: str,
    evidence_numbers: set[str],
    *,
    question: str = "",
) -> bool:
    if claim in evidence_numbers:
        return True
    # Strip leading zeroes e.g. "03" vs "3" or "02" vs "2"
    clean_claim = claim.lstrip("0") or "0"
    if clean_claim in {e.lstrip("0") or "0" for e in evidence_numbers}:
        return True
    # Accept compact amounts such as "26 million" when the source stores
    # "26,000,000". Require at least two digits to avoid matching list labels.
    if len(claim.replace(".", "")) >= 2 and any(
        evidence.startswith(claim.replace(".", ""))
        for evidence in evidence_numbers
        if "." not in evidence
    ):
        return True
    # Tuition and financial amounts: 500 <-> 500.000 / 500000, 26 <-> 26.000.000 / 26000000
    if claim.isdigit():
        int_claim = int(claim)
        for e in evidence_numbers:
            if e.isdigit():
                int_e = int(e)
                if int_e > 0 and (int_claim == int_e * 1000 or int_claim == int_e * 1_000_000):
                    return True
                if int_claim > 0 and (int_e == int_claim * 1000 or int_e == int_claim * 1_000_000):
                    return True
    normalized_question = _normalized(question)
    if re.search(r"\bphần\s*trăm\b|%", normalized_question) and claim.isdigit():
        percentage_ratio = int(claim) / 100
        if any(
            "." in evidence and float(evidence) == percentage_ratio
            for evidence in evidence_numbers
        ):
            return True
    scale = 1_000_000 if "triệu" in normalized_question else (
        1_000 if "nghìn" in normalized_question else 1
    )
    if scale == 1 or not claim.isdigit():
        return False
    return any(
        evidence.isdigit() and int(claim) == int(evidence) * scale
        for evidence in evidence_numbers
    )


def verify_answer_grounding(
    answer: str,
    citations: Sequence[Any],
    *,
    question: str = "",
    contexts: Sequence[Any] = (),
) -> GroundingCheck:
    """Verify answer numbers/codes and grade-table values against citations and full contexts.

    Values copied from the question (document numbers, cohorts, or alternatives)
    are context, not newly generated factual claims. They do not need to occur in
    a shortened citation excerpt, while answer-only values remain fail-closed.
    """
    if not answer.strip() or not citations:
        return GroundingCheck(supported=False, unsupported_claims=("missing_evidence",))

    citation_fields = [_citation_fields(citation) for citation in citations]
    context_texts = [
        str(getattr(c, "text", "") or getattr(c, "content", "") or (c.get("text") if isinstance(c, dict) else "") or (c.get("content") if isinstance(c, dict) else "") or "")
        for c in contexts
    ]
    evidence_parts = [
        " | ".join(
            str(fields.get(key) or "")
            for key in (
                "document_number",
                "source",
                "article",
                "clause",
                "section",
                "page",
                "excerpt",
            )
        )
        for fields in citation_fields
    ]
    evidence = "\n".join(evidence_parts + [t for t in context_texts if t])
    normalized_evidence = _normalized(evidence)
    evidence_numbers = _numbers(evidence)
    question_numbers = _numbers(question)
    question_identifiers = {
        _normalized(value) for value in extract_alphanumeric_identifiers(question)
    }
    unsupported: list[str] = []

    for claim in sorted(_numbers(answer)):
        if claim not in question_numbers and not _number_supported(
            claim,
            evidence_numbers,
            question=f"{question}\n{evidence}",
        ):
            unsupported.append(f"number:{claim}")

    for identifier in extract_alphanumeric_identifiers(answer):
        if (
            _normalized(identifier) not in question_identifiers
            and _normalized(identifier) not in normalized_evidence
        ):
            unsupported.append(f"identifier:{identifier}")

    # A table may contain several valid numbers on different rows. When an
    # answer names a grade, require its claimed values to occur on that row,
    # preventing the classic A+/A row-column mix-up.
    table_lines = [line for line in evidence.splitlines() if "|" in line]
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", answer):
        labels = {label.upper() for label in GRADE_RE.findall(sentence)}
        if not labels:
            continue
        sentence_numbers = _numbers(sentence)
        for label in labels:
            matching_rows = [
                row
                for row in table_lines
                if re.search(rf"(?<!\w){re.escape(label)}(?!\w)", row, re.IGNORECASE)
            ]
            row_numbers = _numbers("\n".join(matching_rows))
            # A grade-only statement (for example, "đạt từ D trở lên") does
            # not claim a numeric table value. Only compare row numbers when
            # the answer sentence actually contains a number; otherwise a
            # valid grade threshold is rejected merely because the source row
            # also happens to contain numeric columns.
            if (
                sentence_numbers
                and row_numbers
                and sentence_numbers.isdisjoint(row_numbers)
            ):
                unsupported.extend(
                    f"table_row:{label}:{number}"
                    for number in sorted(sentence_numbers)
                )

    return GroundingCheck(
        supported=not unsupported,
        unsupported_claims=tuple(dict.fromkeys(unsupported)),
    )
