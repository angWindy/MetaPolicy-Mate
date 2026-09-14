from __future__ import annotations

from src.rag.answer_grounding import verify_answer_grounding


def _citation(excerpt: str) -> dict:
    return {
        "document_number": "5445/QĐ-ĐHBK",
        "source": "5445/QĐ-ĐHBK, Điều 12",
        "article": "12",
        "clause": None,
        "page": 10,
        "excerpt": excerpt,
    }


def test_supported_numeric_answer_passes() -> None:
    result = verify_answer_grounding(
        "Điểm A+ là 9,5-10 [1].",
        [_citation("| Điểm chữ | Điểm số |\n| A+ | 9,5÷10 |")],
    )

    assert result.supported is True
    assert result.unsupported_claims == ()


def test_wrong_value_from_adjacent_table_row_fails() -> None:
    result = verify_answer_grounding(
        "Điểm A+ là 8,5-9,4 [1].",
        [
            _citation(
                "| Điểm chữ | Điểm số |\n"
                "| A+ | 9,5÷10 |\n"
                "| A | 8,5÷9,4 |"
            )
        ],
    )

    assert result.supported is False
    assert "table_row:A+:8.5" in result.unsupported_claims


def test_grade_only_claim_is_not_treated_as_numeric_row_claim() -> None:
    result = verify_answer_grounding(
        "Học phần thông thường đạt từ D; học phần tốt nghiệp đạt từ C [1].",
        [
            _citation(
                "| Điểm chữ | Điểm số |\n"
                "| D | 4,0÷4,9 |\n"
                "| C | 5,0÷5,4 |"
            )
        ],
    )

    assert result.supported is True
    assert result.unsupported_claims == ()


def test_percentage_claim_is_supported_by_decimal_weight_in_source() -> None:
    result = verify_answer_grounding(
        "Điểm cuối kỳ có trọng số từ 50% đến 80% [1].",
        [_citation("Điểm cuối kỳ có trọng số từ 0,5 đến 0,8.")],
        question="Trọng số chiếm tối thiểu bao nhiêu phần trăm?",
    )

    assert result.supported is True
    assert result.unsupported_claims == ()


def test_unsupported_student_identifier_fails() -> None:
    result = verify_answer_grounding(
        "Mã 20240798E là Hoàng Văn Mạnh [1].",
        [_citation("20240799E | Hoàng Văn Mạnh | Kỹ thuật vật liệu")],
    )

    assert result.supported is False
    assert "identifier:20240798E" in result.unsupported_claims


def test_citation_markers_and_numbered_lists_are_not_facts() -> None:
    result = verify_answer_grounding(
        "1. Hoàn thành chương trình [1].\n2. Đạt GPA 2,0 [1].",
        [_citation("Sinh viên hoàn thành chương trình và có GPA từ 2,0.")],
    )

    assert result.supported is True


def test_number_copied_from_question_does_not_require_excerpt_support() -> None:
    result = verify_answer_grounding(
        "Theo Quy chế 5445, học phần thông thường đạt từ D [1].",
        [_citation("Học phần được đánh giá đạt từ điểm D trở lên.")],
        question="Theo QĐ 5445, mức điểm đạt tối thiểu là gì?",
    )

    assert result.supported is True


def test_answer_only_number_still_requires_excerpt_support() -> None:
    result = verify_answer_grounding(
        "Thời hạn là 30 ngày [1].",
        [_citation("Thời hạn là 03 tháng.")],
        question="Thời hạn tối đa là bao lâu?",
    )

    assert result.supported is False
    assert "number:30" in result.unsupported_claims


def test_accepts_thousand_unit_conversion_requested_by_question() -> None:
    result = verify_answer_grounding(
        "Mức học phí là 630.000 đồng mỗi tín chỉ [1].",
        [{"excerpt": "Khoa học máy tính: 630"}],
        question="Học phí bao nhiêu nghìn đồng mỗi tín chỉ?",
    )

    assert result.supported


def test_accepts_thousand_conversion_when_unit_is_in_citation_section() -> None:
    result = verify_answer_grounding(
        "Mức học phí là 600.000 đồng mỗi TCHP [1].",
        [
            {
                "section": "Đơn vị nghìn đồng mỗi TCHP",
                "excerpt": "Tài chính - Ngân hàng: 600",
            }
        ],
        question="Học phí Tài chính - Ngân hàng là bao nhiêu mỗi TCHP?",
    )

    assert result.supported
