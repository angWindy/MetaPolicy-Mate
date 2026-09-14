"""Carry section headings into chunk retrieval text without changing source text."""

from __future__ import annotations

import re
from typing import Any

_HEADING_RE = re.compile(
    r"^(?:[IVXLCDM]+\.|phụ\s+lục\b|chương\b|mục\b)",
    flags=re.IGNORECASE,
)
_UNIT_CONTEXT_RE = re.compile(
    r"(?:đơn\s+vị\s+)?(?:nghìn|triệu)\s+đồng|đồng\s*/\s*(?:năm|học\s*kỳ)|tchp",
    flags=re.IGNORECASE,
)


def carry_forward_section_headings(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach the nearest preceding heading to lexical text and metadata.

    PDF chunking often places a short heading at the end of one chunk and its
    table in the next. Keeping the heading as retrieval context distinguishes,
    for example, full-time and part-time fee tables while preserving the raw
    chunk text used for citations.
    """

    headings_by_document: dict[str, str] = {}
    units_by_document: dict[str, str] = {}
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        payload = dict(item.get("payload") or {})
        document_id = str(payload.get("document_id") or "")
        heading = headings_by_document.get(document_id, "")
        unit_context = units_by_document.get(document_id, "")
        inherited_context = "\n".join(
            part for part in (heading, unit_context) if part
        )
        if inherited_context:
            item["embedding_text"] = (
                f"{inherited_context}\n"
                f"{item.get('embedding_text') or item.get('text') or ''}"
            )
            existing_section = str(payload.get("section") or "").strip()
            payload["section"] = (
                " | ".join(
                    dict.fromkeys(
                        part
                        for part in (heading, unit_context, existing_section)
                        if part
                    )
                )
            )
        item["payload"] = payload
        enriched.append(item)

        lines = [
            line.strip()
            for line in str(item.get("text") or "").splitlines()
            if line.strip()
        ]
        for line in reversed(lines[-4:]):
            if len(line) <= 200 and _HEADING_RE.search(line):
                headings_by_document[document_id] = line
                break
        for line in reversed(lines[-6:]):
            if len(line) <= 240 and _UNIT_CONTEXT_RE.search(line):
                units_by_document[document_id] = line
                break
    return enriched
