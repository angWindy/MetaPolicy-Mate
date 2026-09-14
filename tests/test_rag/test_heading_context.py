from src.retrieval.heading_context import carry_forward_section_headings


def _candidate(chunk_id: str, text: str) -> dict:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "embedding_text": text,
        "payload": {"document_id": "doc-1"},
    }


def test_carries_a_standalone_heading_into_the_following_table() -> None:
    candidates = [
        _candidate("heading", "I. Các chương trình đào tạo đại học chính quy"),
        _candidate("table", "Khoa học máy tính 630"),
    ]

    enriched = carry_forward_section_headings(candidates)

    assert enriched[1]["embedding_text"].startswith("I. Các chương trình")
    assert enriched[1]["payload"]["section"].startswith("I.")
    assert enriched[1]["text"] == "Khoa học máy tính 630"


def test_carries_a_trailing_heading_without_rewriting_the_previous_chunk() -> None:
    candidates = [
        _candidate(
            "previous",
            "Quy định miễn giảm học phí.\nII. Chương trình vừa làm vừa học",
        ),
        _candidate("table", "Khoa học máy tính 440"),
    ]

    enriched = carry_forward_section_headings(candidates)

    assert enriched[1]["payload"]["section"] == "II. Chương trình vừa làm vừa học"
    assert enriched[0]["text"].endswith("vừa làm vừa học")


def test_preserves_existing_section_beneath_the_inherited_heading() -> None:
    candidates = [
        _candidate("heading", "I. Các chương trình đào tạo đại học chính quy"),
        {
            **_candidate("table", "Khoa học máy tính 630"),
            "payload": {
                "document_id": "doc-1",
                "section": "Điều 2 — Khoản 1",
            },
        },
    ]

    enriched = carry_forward_section_headings(candidates)

    assert enriched[1]["payload"]["section"] == (
        "I. Các chương trình đào tạo đại học chính quy | Điều 2 — Khoản 1"
    )


def test_carries_monetary_unit_context_into_following_table() -> None:
    candidates = [
        _candidate(
            "unit",
            "Mức học phí được tính theo đơn vị nghìn đồng mỗi TCHP\nnhư sau:",
        ),
        _candidate("heading", "I. Các chương trình đào tạo đại học chính quy"),
        _candidate("table", "Tài chính - Ngân hàng: 600"),
    ]

    enriched = carry_forward_section_headings(candidates)

    assert "nghìn đồng" in enriched[2]["payload"]["section"]
    assert enriched[2]["embedding_text"].startswith("I. Các chương trình")
