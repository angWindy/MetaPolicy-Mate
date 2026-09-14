"""Chunk sections into retrieval units with stable IDs and rich metadata."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable

from src.domain.schemas import ChunkData, DocumentMetadata, SectionData

TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


def _split_long_text(text: str, max_chars: int, overlap_chars: int) -> Iterable[str]:
    if len(text) <= max_chars:
        yield text
        return

    sentences = re.split(r"(?<=[.!?;:])\s+|\n+", text)
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current}\n{sentence}".strip()
        if current and len(candidate) > max_chars:
            yield current
            overlap = current[-overlap_chars:] if overlap_chars else ""
            current = f"{overlap}\n{sentence}".strip()
        else:
            current = candidate
    if current:
        yield current


def _split_markdown_table(
    text: str,
    max_chars: int,
) -> Iterable[tuple[str, dict[str, object]]]:
    """Split a Markdown table only between rows and repeat its column header."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or not TABLE_SEPARATOR_RE.match(lines[1]):
        for part in _split_long_text(text, max_chars=max_chars, overlap_chars=0):
            yield part, {}
        return

    header_lines = lines[:2]
    header = "\n".join(header_lines)
    rows = lines[2:]
    current_rows: list[str] = []
    row_start = 1

    def emit(end: int) -> tuple[str, dict[str, object]]:
        return "\n".join([*header_lines, *current_rows]), {
            "table_header": header_lines[0],
            "table_row_start": row_start,
            "table_row_end": end,
        }

    for row_number, row in enumerate(rows, start=1):
        proposed = "\n".join([header, *current_rows, row])
        if current_rows and len(proposed) > max_chars:
            yield emit(row_number - 1)
            current_rows = [row]
            row_start = row_number
        else:
            current_rows.append(row)
    if current_rows:
        yield emit(len(rows))


def build_chunks(
    *,
    document_id: str,
    version_id: str,
    metadata: DocumentMetadata,
    sections: list[SectionData],
    max_chars: int,
    overlap_chars: int,
) -> list[ChunkData]:
    """Split each section into chunks that respect max_chars; assign section_id."""
    chunks: list[ChunkData] = []
    version_namespace = uuid.UUID(version_id)

    for section_index, section in enumerate(sections):
        # Build the prefix for embedding (title | doc_number | heading)
        heading = " > ".join(section.heading_path) if section.heading_path else ""
        prefix_parts = [metadata.title, metadata.document_number, heading]
        prefix = " | ".join(part for part in prefix_parts if part)

        if section.section_type == "table":
            text_parts = _split_markdown_table(section.text, max_chars=max_chars)
        else:
            text_parts = (
                (text_part, {})
                for text_part in _split_long_text(
                    section.text,
                    max_chars=max_chars,
                    overlap_chars=overlap_chars,
                )
            )

        table_id = str(uuid.uuid5(version_namespace, f"table-{section_index}"))
        for text_part, table_metadata in text_parts:
            chunk_index = len(chunks)
            chunk_id = str(uuid.uuid5(version_namespace, f"chunk-{chunk_index}"))
            payload = {
                "document_id": document_id,
                "version_id": version_id,
                "document_number": metadata.document_number,
                "title": metadata.title,
                # section structure
                "section_type": section.section_type,
                "section_number": section.section_number,
                "heading": section.heading,
                "heading_path": section.heading_path,
                # legacy aliases for existing retrieval code
                "article": section.section_number if section.section_type == "article" else None,
                "clause": section.section_number if section.section_type == "clause" else None,
                "point": section.section_number if section.section_type == "point" else None,
                "section": section.heading,
                "page": section.page,
                # content kind (paragraph/table) for downstream retrieval
                "content_type": section.section_type,
                # OCR provenance: set by ``extract_sections`` when the
                # source page average_confidence < low_confidence_threshold.
                # Retrieval / UI flag these chunks for human review.
                "low_confidence": section.low_confidence,
                # access & validity
                "source_url": metadata.source_url,
                "owner_department": metadata.owner_department,
                "access_level": metadata.access_level.value,
                "allowed_departments": [item.upper() for item in metadata.allowed_departments],
                "effective_from": (metadata.effective_from.isoformat() if metadata.effective_from else None),
                "effective_to": (metadata.effective_to.isoformat() if metadata.effective_to else None),
                "legal_status": "draft",
                "source_section_index": section_index,
                **(
                    {
                        "table_id": table_id,
                        "parent_table_heading": heading or section.heading,
                        **table_metadata,
                    }
                    if section.section_type == "table"
                    else {}
                ),
            }
            chunks.append(
                ChunkData(
                    id=chunk_id,
                    text=text_part,
                    embedding_text=f"{prefix}\n{text_part}".strip(),
                    document_id=document_id,
                    version_id=version_id,
                    section_id=None,  # populated after sections are persisted
                    chunk_index=chunk_index,
                    metadata=payload,
                )
            )
    # Context expansion reads neighbors from PostgreSQL using these canonical
    # payload fields. Persist the stable links during ingestion so multi-clause
    # provisions and split tables can be reconstructed without trusting Qdrant.
    for index, chunk in enumerate(chunks):
        chunk.metadata.update(
            {
                "previous_chunk_id": chunks[index - 1].id if index else None,
                "next_chunk_id": chunks[index + 1].id if index + 1 < len(chunks) else None,
            }
        )
    return chunks
