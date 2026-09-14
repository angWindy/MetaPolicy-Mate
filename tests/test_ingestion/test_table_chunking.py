from __future__ import annotations

from src.domain.schemas import AccessScope, DocumentMetadata, SectionData
from src.ingestion.chunker import build_chunks


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        title="Admission list",
        document_number="10714/TABLE-ĐHBK",
        owner_department="DT",
        access_level=AccessScope.PUBLIC,
        allowed_departments=[],
        version_number="1",
    )


def test_table_chunks_repeat_header_and_never_split_a_row() -> None:
    table = """| Student ID | Full name | Major |
|---|---|---|
| 20240798E | Nguyen Van A | Mechanical Engineering |
| 20240799E | Hoang Van Manh | Materials Engineering |
| 20240800E | Tran Van B | Physics Engineering |"""

    chunks = build_chunks(
        document_id="doc-1",
        version_id="68ca10de-c902-42e3-a0f1-370b479ba44e",
        metadata=_metadata(),
        sections=[
            SectionData(
                section_type="table",
                heading="Admission results",
                heading_path=["Article 1", "Admission results"],
                text=table,
            )
        ],
        max_chars=130,
        overlap_chars=20,
    )

    assert len(chunks) == 3
    assert all("| Student ID | Full name | Major |" in chunk.text for chunk in chunks)
    assert all(chunk.text.count("\n|") == 2 for chunk in chunks)
    assert chunks[1].metadata["table_row_start"] == 2
    assert chunks[1].metadata["table_row_end"] == 2
    assert chunks[1].metadata["table_header"] == "| Student ID | Full name | Major |"
    assert chunks[1].metadata["parent_table_heading"] == (
        "Article 1 > Admission results"
    )
    assert "20240799E | Hoang Van Manh | Materials Engineering" in (
        chunks[1].embedding_text
    )
    assert chunks[1].metadata["previous_chunk_id"] == chunks[0].id
    assert chunks[1].metadata["next_chunk_id"] == chunks[2].id


def test_short_table_remains_one_chunk_with_row_metadata() -> None:
    table = """| Grade | Score |
|---|---|
| A+ | 9.5-10 |"""

    [chunk] = build_chunks(
        document_id="doc-1",
        version_id="68ca10de-c902-42e3-a0f1-370b479ba44e",
        metadata=_metadata(),
        sections=[SectionData(section_type="table", text=table)],
        max_chars=500,
        overlap_chars=20,
    )

    assert chunk.text == table
    assert chunk.metadata["table_row_start"] == 1
    assert chunk.metadata["table_row_end"] == 1
    assert chunk.metadata["content_type"] == "table"
