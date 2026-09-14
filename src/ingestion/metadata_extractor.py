"""Rule-based metadata extractor for document_number and title.

The extractor is the single source of truth for ``document_number`` and
``title`` on the HUST ingest path. It is intentionally deterministic and
never invokes an LLM. The LLM review path was added as an experimental
two-layer hybrid in 2026-08 but reverted in the same iteration because it
made the MVP harder to audit and introduced non-deterministic failure modes
that were worse than the rule's "needs human review" fallback.

The extractor reuses the existing document-number probe
(``src/ingestion/document_number.py``) so that the same shape of number we
recognise at query time is also recognised at ingest time. The title extractor
is a Vietnamese-specific regex that targets the canonical first-page layout
of university decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.ingestion.document_number import DocumentNumberProbe, extract_document_number

# Roughly the same budget the existing ingestion pipeline uses for the
# document-number probe. Limits how much text we hold in memory.
_HEADER_TEXT_CHAR_BUDGET = 6000

# Headings that indicate a legal/university document title is about to follow.
# The list is closed: only add entries that match actual document types we
# expect to ingest. Anything outside this list lands in "needs_human_review".
_TITLE_HEADINGS = (
    "QUYẾT ĐỊNH",
    "THÔNG BÁO",
    "QUY CHẾ",
    "QUY ĐỊNH",
    "HƯỚNG DẪN",
    "BỘ TIÊU CHÍ",
    "TỜ TRÌNH",
    "CHƯƠNG TRÌNH",
    "KẾ HOẠCH",
    "BÁO CÁO",
)

# Leading bullets / decoration that PDF/OCR sometimes inserts before a heading.
# ``•`` / ``‣`` / ``·`` are common bullet chars; ``-`` / ``*`` are markdown
# bullets that survive a sloppy re-export; ``§`` shows up on some legal docs.
_HEADING_LEAD_PREFIX = r"[\s•‣·\-*§]*"

# Trailing OCR noise tolerated on the same line as the heading. We accept
# any whitespace + punctuation noise (``"QUYẾT ĐỊNH ."``, ``"THÔNG BÁO|"``)
# but **not newlines**, so the heading match stays anchored to its own
# line and does not greedily eat the opening parenthesis (or anything else)
# on the following line. The run is bounded (``{0,30}``) so a wholly
# unrelated trailing sentence can't sneak past the heading-line boundary.
_HEADING_TAIL_SUFFIX = r"[^\w\n]{0,30}"

_HEADING_RE = re.compile(
    r"^"
    + _HEADING_LEAD_PREFIX
    + r"("
    + "|".join(re.escape(item) for item in _TITLE_HEADINGS)
    + r")"
    + _HEADING_TAIL_SUFFIX
    + r"$",
    flags=re.MULTILINE | re.UNICODE,
)

# A parenthetical immediately after the heading is the strong signal: most
# decisions place the title in parentheses on the very next line.
#
# The opening ``\(`` is allowed with optional whitespace and one stray
# punctuation char (e.g. ``"(. Về việc ban hành ... )"``). The closing
# ``\)`` accepts the same trailing noise as ``_HEADING_RE``.
#
# Group 1 captures the title text. We also bound the internal ``\s{0,40}``
# so a parenthesised block can't span more than ~40 chars of whitespace
# (i.e. it must be a real title, not random line wraps across an entire
# page).
_PARENTHETICAL_TITLE_RE = re.compile(
    r"^"
    + _HEADING_LEAD_PREFIX
    + r"\(\s*[\W_]?\s*(.+?)\s*[\W_]?\s*\)"
    + _HEADING_TAIL_SUFFIX
    + r"$",
    flags=re.MULTILINE | re.UNICODE,
)

# Multi-line parenthetical: covers the case where OCR splits the parenthetical
# across two or three lines (e.g. ``(... \n V/v ban hành ... \n)``). Bounded
# to three internal newlines so a real title can't accidentally grow into a
# page-spanning match. ``[\s\S]`` includes newlines because we deliberately
# don't pass ``re.DOTALL`` to the primary regex above (we want single-line
# strict matching there); the multi-line variant opt-in.
_PARENTHETICAL_TITLE_MULTILINE_RE = re.compile(
    r"^"
    + _HEADING_LEAD_PREFIX
    + r"\(\s*[\W_]?\s*(.+?)\s*[\W_]?\s*\)"
    + _HEADING_TAIL_SUFFIX
    + r"$",
    flags=re.MULTILINE | re.UNICODE | re.DOTALL,
)

# OCR bracket misreads we routinely see on Vietnamese scans: the ASCII "("
# can be misread as "1", "I", "l", or the half-width katakana "｢"; ")"
# likewise gets turned into "1", "I", "l", "｣", or a stray pipe.
#
# The intent is fallback-only: a strict ``(...)`` match takes precedence,
# these alternatives are tried only when the strict patterns above miss.
# A leading line-position anchor (``^\s*[OPEN]``) keeps the false-positive
# rate down — a stray "1" mid-line won't accidentally open a fake parenthetical.
_OPEN_BRACKETS = "(|1Il｢"
_CLOSE_BRACKETS = "()|I1l｣"

_PARENTHETICAL_TITLE_OCR_TOLERANT_RE = re.compile(
    r"^\s*"
    + r"[" + re.escape(_OPEN_BRACKETS) + r"]"
    + r"\s*[\W_]?\s*(.+?)\s*[\W_]?\s*["
    + re.escape(_CLOSE_BRACKETS)
    + r"]"
    + _HEADING_TAIL_SUFFIX
    + r"$",
    flags=re.MULTILINE | re.UNICODE | re.DOTALL,
)

# Lines that look like boilerplate header/footer and are never the title.
_BOILERPLATE_TOKENS = (
    "CỘNG HÒA",
    "ĐỘC LẬP",
    "BỘ GIÁO DỤC",
    "ĐẠI HỌC BÁCH KHOA",
    "Số:",
    "Số hiệu",
    "Hà Nội,",
    "Ngày",
    "tháng",
    "_____",
    "Trang",
)


@dataclass(frozen=True)
class TitleProbe:
    """Result of the rule-based title extractor."""

    title: str | None
    confidence: float  # 0.0..1.0
    needs_human_review: bool
    rationale: str = ""


@dataclass(frozen=True)
class MetadataExtractionResult:
    """Combined output of the rule extractor for a single document."""

    document_number: str | None
    document_number_confidence: float  # 0.0..1.0
    title: TitleProbe | None
    raw_header_text: str
    needs_human_review: bool
    rationale: str = ""


@dataclass(frozen=True)
class _ExtractedTitle:
    raw: str
    confidence: float
    needs_human_review: bool
    rationale: str


def _join_header_text(blocks: list) -> str:
    """Trim the first ~6 kB of text from a list of ParsedBlock."""
    parts: list[str] = []
    budget = _HEADER_TEXT_CHAR_BUDGET
    for block in blocks:
        text = getattr(block, "text", "") or ""
        if not text:
            continue
        parts.append(text)
        budget -= len(text)
        if budget <= 0:
            break
    return "\n\n".join(parts)


def _extract_title_from_header(text: str) -> _ExtractedTitle:
    """Locate the title inside a Vietnamese university document header."""
    if not text:
        return _ExtractedTitle(
            raw="",
            confidence=0.0,
            needs_human_review=True,
            rationale="header text empty",
        )

    heading_match = _HEADING_RE.search(text)

    # Try the parenthetical patterns in decreasing order of specificity.
    # Each fall-through yields a *lower* confidence (and stays
    # needs_human_review=True) so a strict match always wins, and a
    # multi-line or OCR-misread match still surfaces useful info instead
    # of crashing into the no-heading fallback path.
    paren_candidates = (
        # (regex, confidence, rationale_suffix, require_human_review)
        (_PARENTHETICAL_TITLE_RE, 1.0, "parenthetical-after-heading", False),
        (_PARENTHETICAL_TITLE_MULTILINE_RE, 0.85, "parenthetical-multiline", True),
        (_PARENTHETICAL_TITLE_OCR_TOLERANT_RE, 0.7, "parenthetical-ocr-tolerant", True),
    )

    if heading_match is not None:
        for regex, confidence, rationale, needs_review in paren_candidates:
            paren_match = regex.search(text)
            if (
                paren_match is not None
                and paren_match.start() > heading_match.end()
            ):
                candidate = paren_match.group(1).strip()
                if candidate and not any(
                    token in candidate for token in _BOILERPLATE_TOKENS
                ):
                    return _ExtractedTitle(
                        raw=candidate,
                        confidence=confidence,
                        needs_human_review=needs_review,
                        rationale=rationale,
                    )

    if heading_match is None:
        # No recognised heading. Fall back to the first non-boilerplate line.
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(token in stripped for token in _BOILERPLATE_TOKENS):
                continue
            if len(stripped) < 8:
                continue
            return _ExtractedTitle(
                raw=stripped,
                confidence=0.4,
                needs_human_review=True,
                rationale="no-heading-fallback-first-line",
            )
        return _ExtractedTitle(
            raw="",
            confidence=0.0,
            needs_human_review=True,
            rationale="no-heading-empty-body",
        )

    # Heading found but no parenthetical — take the next non-boilerplate line.
    after_heading = text[heading_match.end():].splitlines()
    for line in after_heading:
        stripped = line.strip()
        if not stripped:
            continue
        if any(token in stripped for token in _BOILERPLATE_TOKENS):
            continue
        if _HEADING_RE.match(stripped):
            break
        return _ExtractedTitle(
            raw=stripped,
            confidence=0.7,
            needs_human_review=True,
            rationale="heading-without-parenthetical",
        )

    return _ExtractedTitle(
        raw="",
        confidence=0.0,
        needs_human_review=True,
        rationale="heading-no-body",
    )


def extract_metadata(
    blocks: list,
    *,
    header_text_override: str | None = None,
    filename_hint: str | None = None,
) -> MetadataExtractionResult:
    """Run the rule-based extractor over parsed blocks.

    Parameters
    ----------
    blocks:
        Parsed block objects from the parser. Only ``.text`` is read.
    header_text_override:
        When the caller already has a flattened header (e.g. tests), pass it
        here to skip re-assembly from ``blocks``.
    filename_hint:
        Optional filename (e.g. ``"5980.pdf"``). When present, the extractor
        uses the leading digits as a strong signal: any OCR/PDF text
        candidate that does not share the same number prefix is dropped,
        and the canonical Vietnamese form ``<n>/QĐ-ĐHBK`` is generated when
        no other candidate reaches ``confidence >= 0.85``. This rescues
        scan-only PDFs where the OCR engine frequently reads ``QĐ`` as
        ``QD`` or ``Q D`` and so cannot match the canonical pattern with
        full confidence.
    """
    header_text = (
        header_text_override if header_text_override is not None else _join_header_text(blocks)
    )
    probe: DocumentNumberProbe = extract_document_number(header_text)
    hint_number = derive_filename_doc_number(filename_hint) if filename_hint else None

    if hint_number is not None:
        probe = _apply_filename_hint(probe, hint_number)

    title = _extract_title_from_header(header_text)

    title_probe = TitleProbe(
        title=title.raw or None,
        confidence=title.confidence,
        needs_human_review=title.needs_human_review,
        rationale=title.rationale,
    )

    needs_human = (
        probe.recommended is None
        or probe.confidence < 0.85
        or probe.needs_human_review
        or title_probe.needs_human_review
    )
    rationale_parts = [
        f"doc={probe.recommended}@{probe.confidence:.2f}",
        f"title={title_probe.title!r}@{title_probe.confidence:.2f}",
    ]
    if hint_number is not None:
        rationale_parts.append(f"filename_hint={hint_number}")
    return MetadataExtractionResult(
        document_number=probe.recommended,
        document_number_confidence=probe.confidence,
        title=title_probe,
        raw_header_text=header_text,
        needs_human_review=needs_human,
        rationale="; ".join(rationale_parts),
    )


_FILENAME_NUMBER_RE = re.compile(r"(\d{2,6})(?:[-_][\w-]+)?\.pdf$", flags=re.IGNORECASE)
_FILENAME_NUMBER_PREFIX_RE = re.compile(r"\b(\d{2,6})/")


def derive_filename_doc_number(filename: str) -> str | None:
    """Return ``"<n>/QĐ-ĐHBK"`` when ``<filename>`` matches the HUST pattern.

    The HUST ingest folder uses filenames like ``5980.pdf`` or
    ``7323.pdf``. We do not have the suffix (e.g. ``QĐ-ĐHBK``) in the
    filename itself, so we fall back to the dominant university suffix used
    by the corpus. This is a *hint*, not the final answer — the OCR text
    still has the final say in ``_apply_filename_hint``.
    """
    if not filename:
        return None
    match = _FILENAME_NUMBER_RE.search(filename)
    if not match:
        return None
    return f"{match.group(1)}/QĐ-ĐHBK"


def _apply_filename_hint(
    probe: DocumentNumberProbe,
    hint: str,
) -> DocumentNumberProbe:
    """Reconcile the heuristic probe with the filename hint.

    Rules:

    * When the probe has no recommendation, adopt the hint at confidence
      0.80 (still requires human review because we are inferring the
      canonical ``QĐ-ĐHBK`` suffix from the filename alone).
    * When the probe's recommendation and the hint share the same number
      prefix (e.g. ``5980/...``), keep the probe but flag confidence as
      1.0 — the hint vouches for the canonical Vietnamese form.
    * When the prefix differs, drop the probe's recommendation entirely
      and surface the hint at confidence 0.0 so a human reviewer takes
      a look.
    """
    if not hint:
        return probe

    prefix_match = _FILENAME_NUMBER_PREFIX_RE.search(hint)
    if not prefix_match:
        return probe
    hint_prefix = prefix_match.group(1)

    if probe.recommended is None:
        return DocumentNumberProbe(
            candidates=(hint,),
            recommended=hint,
            needs_human_review=True,
            confidence=0.80,
            matched_pages={},
        )

    rec_match = _FILENAME_NUMBER_PREFIX_RE.search(probe.recommended)
    rec_prefix = rec_match.group(1) if rec_match else None
    if rec_prefix == hint_prefix:
        # Same number, different OCR spelling (e.g. ``QD-DHBK`` vs ``QĐ-ĐHBK``).
        # Trust the hint for the canonical form.
        return DocumentNumberProbe(
            candidates=(hint,) + probe.candidates,
            recommended=hint,
            needs_human_review=False,
            confidence=1.0,
            matched_pages=probe.matched_pages,
        )

    # Prefix mismatch — OCR saw a different number; flag for human review.
    return DocumentNumberProbe(
        candidates=(hint,) + tuple(
            c for c in probe.candidates if c != hint
        ),
        recommended=hint,
        needs_human_review=True,
        confidence=0.0,
        matched_pages={},
    )
