"""Extract hierarchical legal structure from parsed document blocks.

Digital mode (default) keeps the strict regex set (``Điều\s+\d+``,
``Chương\s+[IVXLCDM]+``, ...) because born-digital PDFs emit canonical
Vietnamese text. ``ocr_mode=True`` adds two relaxations so the same
function can recover structure from raw scan OCR output:

1. :class:`OcrArtifactCleaner` runs on each line before regex matching,
   collapsing the systematic ``Ả``-as-space artefacts PP-OCRv6 emits.
   Idempotent on already-clean text — safe to call defensively.
2. Multi-line article titles are matched: when a line matches
   ``Điều N.`` with no title (or the title is broken across a line
   wrap), the following non-blank line is consumed as the title.

Low-confidence blocks (``ParsedBlock.low_confidence = True``) bypass
regex matching entirely. Each line becomes its own preamble section so
the downstream chunker can split on ``max_chars`` boundaries rather
than guessing at heading structure. This protects RAG retrieval from
shredding a noisy scan into fake article/clause markers.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from src.domain.schemas import ParsedBlock, SectionData
from src.ingestion.pdf_processor.vn_diacritic_restore import (
    OcrArtifactCleaner,
    get_default_cleaner as _get_default_ocr_cleaner,
)

logger = logging.getLogger(__name__)

# Strict regex set — used by default (digital / born-textual PDFs).
ARTICLE_RE = re.compile(r"^\s*Điều\s+([0-9]+[a-zA-Z]?)\s*[.:\-]?\s*(.*)$", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^\s*(Chương|Mục|Phần)\s+([IVXLCDM0-9]+)\b(.*)$", re.IGNORECASE)
CLAUSE_RE = re.compile(r"^\s*([0-9]+)\s*[.)]\s+(.+)$")
POINT_RE = re.compile(r"^\s*([a-zđ])\s*[.)]\s+(.+)$", re.IGNORECASE)

# Heading-only article regex (no title yet). Used to merge the title
# from the next non-blank line in OCR mode. Allows ``.``, ``:`` or ``-``
# after the digit, e.g. ``Điều 1.``, ``Điều 2:``, ``Điều 3-``.
ARTICLE_HEAD_RE = re.compile(
    r"^\s*Điều\s+([0-9]+[a-zA-Z]?)\s*[.:\-]\s*\.?\s*$",
    re.IGNORECASE,
)


def _clean_line(line: str, cleaner: OcrArtifactCleaner | None) -> str:
    """Apply the OCR-artifact cleaner to a single line (or no-op if ``None``)."""
    if cleaner is None or not line:
        return line
    return cleaner.clean(line)


def _split_lines(text: str) -> list[str]:
    """Return non-blank stripped lines from ``text``."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def _emit_preamble(
    text: str,
    *,
    heading_path: list[str],
    page: int | None,
) -> SectionData:
    """Emit a preamble section (no structure) for a body line."""
    return SectionData(
        section_type="preamble",
        section_number=None,
        heading=None,
        heading_path=heading_path.copy(),
        page=page,
        text=text,
    )


def _append_to_last_section(
    sections: list[SectionData],
    line: str,
    page: int | None,
) -> None:
    """Append ``line`` to the last existing section, or create preamble."""
    if sections:
        sections[-1].text = f"{sections[-1].text}\n{line}".strip()
        if sections[-1].page is None:
            sections[-1].page = page
    else:
        sections.append(
            SectionData(
                section_type="preamble",
                section_number=None,
                heading=None,
                heading_path=[],
                page=page,
                text=line,
            )
        )


def extract_sections(
    blocks: list[ParsedBlock],
    *,
    ocr_mode: bool = False,
    cleaner: OcrArtifactCleaner | None = None,
) -> list[SectionData]:
    """Parse parsed blocks into a flat list of legal sections.

    Args:
        blocks: Output of :func:`DocumentParser.parse`.
        ocr_mode: When ``True`` (default ``False``), apply OCR-specific
            relaxations:

            * Run :class:`OcrArtifactCleaner` per line before regex.
            * Handle multi-line article titles (``Điều N.`` on one
              line, title on the next).
            * Fall back to preamble-only extraction for blocks whose
              ``low_confidence`` flag is set.

            The mode is auto-inferred: if any block carries
            ``low_confidence=True`` we still apply OCR cleanup to the
            rest of the page. Operators can force strict mode by
            passing ``ocr_mode=False`` explicitly even with OCR-sourced
            blocks.
        cleaner: Optional pre-built :class:`OcrArtifactCleaner`. When
            ``None`` and ``ocr_mode=True`` we use the module-level
            singleton (``get_default_cleaner()``).

    Returns:
        A flat list of :class:`SectionData` with chapter / article /
        clause / point / table / preamble types. Empty sections (no
        text) are dropped on the way out.
    """
    if ocr_mode and cleaner is None:
        cleaner = _get_default_ocr_cleaner()

    sections: list[SectionData] = []
    heading_stack: list[str] = []
    current_chapter: str | None = None
    current_article: str | None = None
    current_clause: str | None = None

    for block in blocks:
        text = block.text
        page = block.page
        block_low_conf = bool(getattr(block, "low_confidence", False))

        # Tables are reserved as a single opaque section so the Markdown
        # structure (column separators, header row) is preserved end-to-end.
        if block.block_type == "table":
            heading_path = heading_stack.copy()
            heading = "Bảng"
            if current_article:
                heading = f"Điều {current_article} — Bảng"
                heading_path = (
                    [current_chapter] if current_chapter else []
                ) + [f"Điều {current_article}", "Bảng"]
            sections.append(
                SectionData(
                    section_type="table",
                    section_number=current_article,
                    heading=heading,
                    heading_path=heading_path,
                    page=page,
                    text=text,
                    low_confidence=block_low_conf,
                )
            )
            continue

        # Low-confidence OCR: never trust regex heading detection on
        # these blocks. Each non-blank line becomes its own preamble
        # section so build_chunks can split on ``max_chars`` boundaries
        # without producing fake ``Điều X`` markers.
        if block.low_confidence:
            for line in _split_lines(text):
                if sections:
                    sections[-1].text = f"{sections[-1].text}\n{line}".strip()
                    if sections[-1].page is None:
                        sections[-1].page = page
                    sections[-1].low_confidence = True
                else:
                    sections.append(
                        SectionData(
                            section_type="preamble",
                            section_number=None,
                            heading=None,
                            heading_path=[],
                            page=page,
                            text=line,
                            low_confidence=True,
                        )
                    )
            continue

        cleaned_lines: Iterable[str] = (
            _clean_line(line, cleaner) for line in _split_lines(text)
        )
        # Need to peek for multi-line title support. Iterate manually.
        line_iter = iter(cleaned_lines)
        lines_buffered: list[str] = list(line_iter)

        i = 0
        while i < len(lines_buffered):
            line = lines_buffered[i]

            chapter_match = CHAPTER_RE.match(line)
            if chapter_match:
                group0, group1, group2 = chapter_match.groups()
                current_chapter = f"{group0} {group1}"
                current_article = current_clause = None
                heading_stack = [current_chapter]
                if group2.strip():
                    heading_stack.append(group2.strip())
                sections.append(
                    SectionData(
                        section_type="chapter",
                        section_number=group1.strip(),
                        heading=current_chapter,
                        heading_path=heading_stack.copy(),
                        page=page,
                        text=line,
                        low_confidence=block_low_conf,
                    )
                )
                i += 1
                continue

            article_match = ARTICLE_RE.match(line)
            if not article_match and ocr_mode:
                # OCR mode: also try the heading-only form so we can
                # consume the next non-blank line as the title.
                head_match = ARTICLE_HEAD_RE.match(line)
                if head_match:
                    article_num = head_match.group(1)
                    title = ""
                    if i + 1 < len(lines_buffered):
                        candidate = lines_buffered[i + 1].strip()
                        # Only consume the next line as title when it
                        # doesn't look like a clause / point / chapter
                        # marker itself. Heading regex on candidate would
                        # double-merge.
                        if not (
                            CLAUSE_RE.match(candidate)
                            or POINT_RE.match(candidate)
                            or CHAPTER_RE.match(candidate)
                            or ARTICLE_RE.match(candidate)
                            or ARTICLE_HEAD_RE.match(candidate)
                        ):
                            title = candidate
                            i += 1
                    current_article = article_num
                    current_clause = None
                    heading = f"Điều {current_article}"
                    if title:
                        heading = f"{heading}. {title}"
                    heading_stack = [current_chapter] if current_chapter else []
                    heading_stack.append(heading)
                    sections.append(
                        SectionData(
                            section_type="article",
                            section_number=current_article,
                            heading=heading,
                            heading_path=heading_stack.copy(),
                            page=page,
                            text=line if not title else f"{line}\n{title}",
                            low_confidence=block_low_conf,
                        )
                    )
                    i += 1
                    continue

            if article_match:
                current_article = article_match.group(1)
                current_clause = None
                heading = f"Điều {current_article}"
                title = article_match.group(2).strip()
                if title:
                    heading = f"{heading}. {title}"
                heading_stack = [current_chapter] if current_chapter else []
                heading_stack.append(heading)
                sections.append(
                    SectionData(
                        section_type="article",
                        section_number=current_article,
                        heading=heading,
                        heading_path=heading_stack.copy(),
                        page=page,
                        text=line,
                        low_confidence=block_low_conf,
                    )
                )
                i += 1
                continue

            clause_match = CLAUSE_RE.match(line)
            if clause_match and current_article:
                current_clause = clause_match.group(1)
                heading = f"Điều {current_article} — Khoản {current_clause}"
                heading_stack = [current_chapter] if current_chapter else []
                heading_stack.extend([f"Điều {current_article}", f"Khoản {current_clause}"])
                sections.append(
                    SectionData(
                        section_type="clause",
                        section_number=current_clause,
                        heading=heading,
                        heading_path=heading_stack.copy(),
                        page=page,
                        text=line,
                        low_confidence=block_low_conf,
                    )
                )
                i += 1
                continue

            point_match = POINT_RE.match(line)
            if point_match and current_article:
                point_num = point_match.group(1).lower()
                heading = f"Điều {current_article}"
                if current_clause:
                    heading = f"{heading} — Khoản {current_clause}"
                heading = f"{heading} — Điểm {point_num}"
                heading_stack = [current_chapter] if current_chapter else []
                heading_stack.extend([f"Điều {current_article}"])
                if current_clause:
                    heading_stack.append(f"Khoản {current_clause}")
                heading_stack.append(f"Điểm {point_num}")
                sections.append(
                    SectionData(
                        section_type="point",
                        section_number=point_num,
                        heading=heading,
                        heading_path=heading_stack.copy(),
                        page=page,
                        text=line,
                        low_confidence=block_low_conf,
                    )
                )
                i += 1
                continue

            # Fallback: append to the last section's text body
            _append_to_last_section(sections, line, page)
            if sections:
                sections[-1].low_confidence = (
                    sections[-1].low_confidence or block_low_conf
                )
            i += 1

    return [item for item in sections if item.text.strip()]
