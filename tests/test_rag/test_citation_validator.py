from __future__ import annotations

from datetime import date

import pytest

from src.domain.schemas import Citation, GeneratedAnswer, RetrievedChunk, UserContext
from src.rag.citation_validator import (
    build_citation_allowlist,
    build_citations,
    build_focused_excerpt,
    mark_answer_unverified,
    validate_and_build_citations,
    validate_citation_chunk_ids,
    validate_document_versions,
    validate_source_locations,
)


def test_focused_excerpt_keeps_table_header_and_matching_identifier_row():
    rows = [
        "| TT | Họ và tên | Mã học viên | Ngành |",
        "|---|---|---|---|",
        *[
            f"| {index} | Sinh viên {index} | 20240{index:03d}E | Cơ khí |"
            for index in range(1, 40)
        ],
        "| 40 | Hoàng Văn Mạnh | 20240799E | Kỹ thuật vật liệu |",
    ]

    excerpt = build_focused_excerpt(
        "\n".join(rows),
        "Ai có mã 20240799E và học ngành gì?",
    )

    assert "Họ và tên" in excerpt
    assert "Hoàng Văn Mạnh" in excerpt
    assert "20240799E" in excerpt
    assert "Kỹ thuật vật liệu" in excerpt


def test_focused_excerpt_aligns_a_horizontal_grade_table():
    content = (
        "Điểm học phần theo thang 10 8,0÷ 8,4 8,5÷ 9,4 9,5÷ 10 "
        "Điểm chữ quy đổi B+ A A+ Điểm số quy đổi 3,5 4,0 4,0"
    )

    excerpt = build_focused_excerpt(content, "Điểm A+ nằm trong khoảng nào?")

    assert "| A+ | 9,5÷ 10 |" in excerpt


def test_focused_excerpt_aligns_jlpt_with_vietnamese_framework_level():
    content = (
        "Bảng xếp bậc các chứng chỉ tiếng Nhật. "
        "JLPT N5 N4 N3 N2 N1\n"
        "Bậc trình độ theo KNLNNVN Bậc 2 Bậc 3 Bậc 4 Bậc 5 Bậc 6"
    )

    excerpt = build_focused_excerpt(content, "JLPT N5 được quy đổi sang bậc nào?")

    assert "JLPT N5 N4 N3 N2 N1" in excerpt
    assert "Bậc 2 Bậc 3 Bậc 4 Bậc 5 Bậc 6" in excerpt
    assert "| N5 | Bậc 2 |" in excerpt


def test_focused_excerpt_keeps_vietnam_japan_program_with_its_outcome():
    content = (
        "Chuẩn đầu ra khi xét tốt nghiệp Đạt chứng chỉ tiếng Nhật từ N3\n"
        "Hoặc đạt toàn bộ các học phần tiếng Nhật gồm:\n"
        "{JP1111, JP1121, JP1134, JP2113}\n"
        "Bảng 7.3 Danh mục học phần tiếng Nhật với chương\n"
        "trình Công nghệ thông tin Việt - Nhật\n"
        "1 JP1110 Tiếng Nhật 1\n"
        "Chuẩn đầu ra khi xét tốt nghiệp Đạt chứng chỉ tiếng Nhật từ N3\n"
        "Hoặc đạt toàn bộ các học phần tiếng Nhật gồm:\n"
        "{JP1110, JP1120, JP1132, JP2111}"
    )

    excerpt = build_focused_excerpt(
        content,
        "Chuẩn đầu ra Công nghệ thông tin Việt - Nhật là gì?",
    )

    assert "Công nghệ thông tin Việt - Nhật" in excerpt
    assert "Đạt chứng chỉ tiếng Nhật từ N3" in excerpt
    assert "{JP1110, JP1120, JP1132, JP2111}" in excerpt


def context(
    chunk_id: str = "chunk-1",
    *,
    document_id: str = "doc-1",
    version_id: str = "version-1",
    page: int | None = 3,
    section: str | None = "Điều 5",
    source_url: str | None = "https://example.edu/rules/1",
    allowed_units: list[str] | None = None,
    allowed_roles: list[str] | None = None,
    classification: str = "internal",
    tenant_id: str = "hust",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text="Nội dung quy định tại Điều 5.",
        score=0.95,
        source="hybrid",
        metadata={
            "document_id": document_id,
            "version_id": version_id,
            "document_number": "01/QĐ",
            "title": "Quy định thử nghiệm",
            "article": "5",
            "section": section,
            "page": page,
            "source_url": source_url,
            "legal_status": "effective",
            "tenant_id": tenant_id,
            "status": "published",
            "classification": classification,
            "allowed_roles": allowed_roles or ["staff"],
            "allowed_units": allowed_units or ["TCCB"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
        },
    )


def staff_user() -> UserContext:
    return UserContext(
        user_id="u-1",
        tenant_id="hust",
        department="TCCB",
        roles={"staff"},
        clearance_level="internal",
    )


def valid_citation(item: RetrievedChunk | None = None, **updates) -> Citation:
    item = item or context()
    metadata = {**item.metadata, **updates}
    return Citation(
        chunk_id=item.chunk_id,
        document_id=metadata["document_id"],
        version_id=metadata["version_id"],
        document_number=metadata["document_number"],
        title=metadata["title"],
        source=metadata.get("source_url") or "01/QĐ, Điều 5",
        source_url=metadata.get("source_url"),
        article=metadata.get("article"),
        section=metadata.get("section"),
        page=metadata.get("page"),
        excerpt=item.text,
    )


def test_allowlist_and_build_citations_copy_only_context_metadata():
    item = context()
    allowlist = build_citation_allowlist([item], user=staff_user())
    citations = build_citations(["chunk-1"], allowlist)

    assert set(allowlist) == {"chunk-1"}
    assert citations[0].page == 3
    assert citations[0].section == "Điều 5"
    assert citations[0].source_url == item.metadata["source_url"]


def test_adversarial_fake_chunk_id_is_rejected_and_answer_unverified():
    item = context()
    generated = GeneratedAnswer(answer="Kết luận", cited_chunk_ids=["fake-chunk"])

    assert validate_citation_chunk_ids(generated.cited_chunk_ids, [item]) == ["fake-chunk"]
    validated, citations = validate_and_build_citations(generated, [item])

    assert citations == []
    assert validated.confidence == "low"
    assert "chưa thể xác minh" in validated.answer


def test_old_document_version_is_rejected_even_when_chunk_id_is_known():
    item = context(version_id="version-current")
    citation = valid_citation(item, version_id="version-old")

    errors = validate_document_versions([citation], [item])

    assert errors
    assert "version_id" in errors[0]


def test_outside_permission_is_excluded_from_allowlist():
    item = context(allowed_units=["OTHER"])
    user = staff_user()

    allowlist = build_citation_allowlist([item], user=user, as_of=date(2026, 8, 5))

    assert allowlist == {}
    assert validate_citation_chunk_ids([item.chunk_id], allowlist) == [item.chunk_id]


@pytest.mark.parametrize(
    "missing_field",
    [
        "tenant_id",
        "status",
        "classification",
        "allowed_roles",
        "allowed_units",
        "valid_from",
    ],
)
def test_missing_required_security_metadata_is_rejected(missing_field: str):
    item = context()
    metadata = dict(item.metadata)
    metadata.pop(missing_field)
    malformed = item.model_copy(update={"metadata": metadata})

    assert build_citation_allowlist([malformed], user=staff_user()) == {}


def test_empty_metadata_is_rejected():
    item = context().model_copy(update={"metadata": {}})

    assert build_citation_allowlist([item], user=staff_user()) == {}


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("tenant_id", 123),
        ("status", ["published"]),
        ("classification", {"level": "public"}),
        ("allowed_roles", "staff"),
        ("allowed_units", {"TCCB"}),
        ("valid_from", ["2026-01-01"]),
    ],
)
def test_invalid_security_metadata_types_are_rejected(field: str, invalid_value):
    item = context()
    malformed = item.model_copy(
        update={"metadata": {**item.metadata, field: invalid_value}}
    )

    assert build_citation_allowlist([malformed], user=staff_user()) == {}


def test_cross_tenant_source_is_rejected():
    assert build_citation_allowlist(
        [context(tenant_id="other-tenant")],
        user=staff_user(),
    ) == {}


def test_role_not_allowed_is_rejected():
    assert build_citation_allowlist(
        [context(allowed_roles=["manager"], allowed_units=["OTHER"])],
        user=staff_user(),
    ) == {}


def test_unit_not_allowed_is_rejected():
    assert build_citation_allowlist(
        [context(allowed_roles=["manager"], allowed_units=["OTHER"])],
        user=staff_user(),
    ) == {}


def test_valid_public_document_is_allowed_with_explicit_acl():
    public_user = staff_user().model_copy(update={"clearance_level": "public"})
    item = context(
        classification="public",
        allowed_roles=["*"],
        allowed_units=["*"],
    )

    assert set(build_citation_allowlist([item], user=public_user)) == {item.chunk_id}


def test_missing_authenticated_user_context_is_rejected():
    assert build_citation_allowlist([context()], user=None) == {}


def test_missing_page_is_rejected_when_context_has_page():
    item = context(page=3)
    citation = valid_citation(item, page=None)

    errors = validate_source_locations([citation], [item])

    assert any("page" in error for error in errors)


def test_wrong_document_is_rejected_even_with_valid_chunk_id():
    item = context()
    citation = valid_citation(item, document_id="other-doc")

    errors = validate_document_versions([citation], [item])

    assert any("document_id" in error for error in errors)


def test_llm_cannot_add_url_not_present_in_context():
    item = context(source_url=None)
    citation = valid_citation(item, source_url="https://attacker.example/fake")

    errors = validate_source_locations([citation], [item])

    assert any("URL" in error for error in errors)


def test_indexed_local_source_path_is_grounded():
    source_path = "/srv/data/raw/HUST/5445.pdf"
    item = context(source_url=source_path)
    citation = valid_citation(item)

    assert validate_source_locations([citation], [item]) == []


def test_mark_answer_unverified_clears_model_supplied_citations():
    answer = mark_answer_unverified(
        GeneratedAnswer(answer="Should not be trusted", cited_chunk_ids=["chunk-1"]),
        ["wrong source location"],
    )

    assert answer.cited_chunk_ids == []
    assert answer.confidence == "low"
    assert "wrong source location" in answer.warnings
