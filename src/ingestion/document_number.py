"""Heuristic document-number extraction from raw text.

Re-uses `DOCUMENT_NUMBER_PATTERN` from the retrieval layer so that the same
shape (`123/QĐ-BYT`, `456/CV-ABC`, ...) is recognised at both query time and
ingestion time. The extractor is intentionally rule-based; it never asks the
LLM. The caller (ingestion pipeline) is responsible for deciding whether the
result is reliable enough to commit to `DocumentMetadata.document_number` or
should be flagged for human review.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from src.retrieval.query_transform import DOCUMENT_NUMBER_PATTERN

# Sentinel value callers (HTTP layer, batch jobs) can pass in
# `DocumentMetadata.document_number` to opt into auto-extraction instead of
# having to invent a placeholder themselves. Kept in this module so the
# ingestion pipeline and the route layer agree on the exact spelling.
AUTO_DETECT_SENTINEL = "__AUTO_DETECT__"


@dataclass(frozen=True)
class DocumentNumberProbe:
    """Result of running the heuristic extractor over a chunk of text.

    Attributes:
        candidates: All distinct numbers found, ordered by descending count.
        recommended: Best-guess value when extraction looks unambiguous.
        needs_human_review: True when caller must verify before relying on
            `recommended` (no matches, multiple candidates, or low confidence).
        confidence: ``1.0`` when exactly one unique match with no ambiguity,
            otherwise a value in ``[0.0, 0.9]`` proportional to how strongly
            one candidate dominates. Callers MUST treat any value below
            ``1.0`` as needing human confirmation.
    """

    candidates: tuple[str, ...]
    recommended: str | None
    needs_human_review: bool
    confidence: float
    matched_pages: dict[str, tuple[int, ...]]  # candidate -> sorted page numbers

    @property
    def matched(self) -> bool:
        return bool(self.candidates)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_header_line(line: str) -> bool:
    """Vietnamese headers such as 'Số: 123/QĐ-ĐHBK' or 'Số hiệu: ...'."""
    stripped = line.strip()
    if not stripped:
        return False
    head_match = re.match(
        r"^(?:s[ốo]\s*(?:hi[ệe]u)?|so\s*(?:hieu)?|s[ốo])\s*[:\-]?\s*",
        stripped,
        flags=re.IGNORECASE,
    )
    return head_match is not None


def extract_document_number(
    text: str,
    *,
    header_max_pages: int = 2,
) -> DocumentNumberProbe:
    """Run the heuristic extractor over plain text.

    The probe scans only the first few "pages" worth of text (the
    configurable ``header_max_pages`` argument, default 2) because
    Vietnamese legal documents place the document number near the top of the
    first page, not in the body. Callers that already have richer structure
    (e.g. a list of `ParsedBlock` objects) should join the early blocks
    and pass the resulting string.

    Returns a :class:`DocumentNumberProbe`. The `recommended` field is set
    only when there is exactly one unique candidate and it appears at least
    twice — once in the explicit header line if any, once in the body — or
    when it appears in an explicit "Số/Số hiệu: ..." line. Otherwise the
    caller MUST treat the result as `needs_human_review=True`.
    """
    if not text or not text.strip():
        return DocumentNumberProbe(
            candidates=(),
            recommended=None,
            needs_human_review=True,
            confidence=0.0,
            matched_pages={},
        )

    normalized = _normalize(text)
    matches = DOCUMENT_NUMBER_PATTERN.findall(normalized)
    if not matches:
        return DocumentNumberProbe(
            candidates=(),
            recommended=None,
            needs_human_review=True,
            confidence=0.0,
            matched_pages={},
        )

    # Weight matches: an occurrence on a "Số: ..." header line counts twice
    # because it is exactly the kind of explicit annotation the caller will
    # be looking for. We approximate "page" boundaries by paragraph splits
    # since the caller may pass concatenated text from multiple pages.
    paragraphs = re.split(r"\n\s*\n", text)
    counter: Counter[str] = Counter()
    matched_paragraphs: dict[str, set[int]] = {}
    for para_index, paragraph in enumerate(paragraphs[: max(1, header_max_pages) * 4]):
        if not paragraph.strip():
            continue
        para_norm = _normalize(paragraph)
        for found in DOCUMENT_NUMBER_PATTERN.findall(para_norm):
            weight = 2 if _is_header_line(paragraph) else 1
            counter[found] += weight
            matched_paragraphs.setdefault(found, set()).add(para_index)

    if not counter:
        # Fallback to raw matches if paragraph slicing failed for some reason.
        for found in matches:
            counter[found] += 1
            matched_paragraphs.setdefault(found, set())

    candidates = tuple(item for item, _ in counter.most_common())
    matched_pages = {
        candidate: tuple(sorted(paragraphs))
        for candidate, paragraphs in matched_paragraphs.items()
    }

    if len(candidates) == 1:
        only = candidates[0]
        # Single candidate. We can recommend it, but confidence is still
        # < 1.0 unless it appears in an explicit "Số:" line so that callers
        # downstream always have a way to require human sign-off.
        in_header = any(_is_header_line(p) for p in paragraphs[: header_max_pages * 4] if only in p)
        confidence = 1.0 if in_header else 0.85
        return DocumentNumberProbe(
            candidates=candidates,
            recommended=only,
            needs_human_review=not in_header,
            confidence=confidence,
            matched_pages=matched_pages,
        )

    # Multiple candidates: always human review. We still expose the
    # top-ranked candidate so reviewers see the leading guess.
    top = candidates[0]
    top_count = counter[top]
    total = sum(counter.values())
    confidence = round(top_count / total, 3) if total else 0.0
    return DocumentNumberProbe(
        candidates=candidates,
        recommended=top,
        needs_human_review=True,
        confidence=confidence,
        matched_pages=matched_pages,
    )
