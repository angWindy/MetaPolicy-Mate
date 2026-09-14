from __future__ import annotations

from src.domain.schemas import Candidate
from src.retrieval.lexical_reranker import LexicalFallbackReranker
from src.retrieval.relevance import (
    contains_requested_numeric_answer,
    corpus_lexical_relevance_scores,
    lexical_relevance_score,
)


def _candidate(chunk_id: str, content: str) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id="doc-1",
        version_id="version-1",
        content=content,
        metadata={"document_number": "10714/TABLE-ĐHBK"},
        fusion_score=0.1,
    )


def test_row_aware_score_prefers_the_row_with_the_named_student() -> None:
    query = "Mã số 20240799E học ngành gì?"
    correct = "| 20240799E | Hoàng Văn Mạnh | Kỹ thuật vật liệu |"
    wrong = "| 20240798E | Nguyễn Văn A | Cơ khí |"

    assert lexical_relevance_score(query, correct) > lexical_relevance_score(
        query, wrong
    )


def test_document_number_and_provision_terms_both_affect_ranking() -> None:
    query = "5445/QĐ-ĐHBK quy định cảnh báo học tập thế nào?"
    relevant = "Điều 19. Cảnh báo học tập. Nâng một mức cảnh báo."
    generic = "Quy chế đào tạo theo Quyết định 5445/QĐ-ĐHBK."

    assert lexical_relevance_score(
        query,
        relevant,
        {"document_number": "5445/QĐ-ĐHBK"},
    ) > lexical_relevance_score(
        query,
        generic,
        {"document_number": "5445/QĐ-ĐHBK"},
    )


def test_lexical_fallback_uses_structured_relevance_features() -> None:
    reranker = LexicalFallbackReranker("fallback")
    scores = reranker.rerank_batch(
        "Mã số 20240799E học ngành gì?",
        [
            _candidate("wrong", "20240798E | Nguyễn Văn A | Cơ khí"),
            _candidate(
                "correct",
                "20240799E | Hoàng Văn Mạnh | Kỹ thuật vật liệu",
            ),
        ],
    )

    assert scores[1] > scores[0]


def test_local_concept_density_beats_a_generic_tuition_heading() -> None:
    query = (
        "Theo QĐ 10232, chương trình Khoa học máy tính hệ chính quy chuẩn "
        "có học phí bao nhiêu mỗi TCHP?"
    )
    generic = (
        "Mức học phí các chương trình đào tạo đại học hệ chính quy, kỹ sư "
        "chuyên sâu và sau đại học theo đơn vị nghìn đồng mỗi TCHP."
    )
    exact_row = (
        "Các chương trình đào tạo chuẩn: Khoa học máy tính, Kỹ thuật máy "
        "tính: 630 nghìn đồng/TCHP."
    )

    assert lexical_relevance_score(query, exact_row) > lexical_relevance_score(
        query, generic
    )


def test_local_concept_density_prefers_the_matching_program_table_row() -> None:
    query = (
        "Chương trình kỹ sư cho người tốt nghiệp cử nhân theo chương trình "
        "tích hợp có thời gian và khối lượng tối thiểu thế nào?"
    )
    definition = (
        "CTĐT tích hợp là chương trình được thiết kế tổng thể. Thời gian tối "
        "đa hoàn thành chương trình kỹ sư là 5,5 năm."
    )
    exact_row = (
        "Kỹ sư | Tốt nghiệp cử nhân theo chương trình tích hợp | "
        "1,5 năm | 48 tín chỉ"
    )

    assert lexical_relevance_score(query, exact_row) > lexical_relevance_score(
        query, definition
    )


def test_corpus_relative_phrases_prefer_specific_standard_program() -> None:
    query = "Chuẩn tiếng Anh đầu ra khi xét tốt nghiệp CTĐT chuẩn là bậc nào?"
    contents = [
        (
            "Chuẩn đầu ra khi xét tốt nghiệp với CTĐT chuẩn: đạt chứng chỉ "
            "trình độ tối thiểu Bậc 3."
        ),
        (
            "Bảng chương trình tăng cường ngoại ngữ. Chuẩn đầu ra khi xét tốt "
            "nghiệp: đạt chứng chỉ tối thiểu Bậc 4."
        ),
    ]

    scores = corpus_lexical_relevance_scores(query, contents)

    assert scores[0] > scores[1]


def test_exact_plus_grade_beats_a_generic_scale_conversion_table() -> None:
    query = "Khoảng điểm thang 10 nào tương ứng điểm A+?"
    grade_table = "Điểm thang 10 9,5 đến 10. Điểm chữ quy đổi A+."
    generic_conversion = "Dải điểm thang 10 tương đương 9,0 đến tròn 10."

    assert lexical_relevance_score(query, grade_table) > lexical_relevance_score(
        query, generic_conversion
    )


def test_numeric_tuition_row_beats_a_unit_only_heading() -> None:
    query = "Học phí Khoa học máy tính bao nhiêu nghìn đồng mỗi TCHP?"
    exact_row = "Khoa học máy tính: 630 nghìn đồng/TCHP."
    heading = "Mức học phí được quy định theo đơn vị nghìn đồng/TCHP."

    assert lexical_relevance_score(query, exact_row) > lexical_relevance_score(
        query, heading
    )


def test_count_answer_row_beats_a_row_that_only_mentions_the_noun() -> None:
    query = "Lịch xét tốt nghiệp gồm mấy đợt?"
    exact_row = "Xét tốt nghiệp theo 03 đợt trong năm."
    generic = "Hai chương trình phải đăng ký tốt nghiệp cùng đợt."

    assert lexical_relevance_score(query, exact_row) > lexical_relevance_score(
        query, generic
    )


def test_yearly_fee_unit_beats_extension_semester_fee() -> None:
    query = "Học phí tiến sĩ là bao nhiêu mỗi năm?"
    annual = "Tiến sĩ: 26 triệu đồng/năm."
    extension = "Gia hạn thời gian học tập: 5 triệu đồng/học kỳ."

    assert lexical_relevance_score(query, annual) > lexical_relevance_score(
        query, extension
    )
    assert contains_requested_numeric_answer(query, annual)
    assert not contains_requested_numeric_answer(query, extension)


def test_full_time_heading_beats_part_time_table_for_same_program() -> None:
    query = "Học phí Tài chính - Ngân hàng hệ chính quy chuẩn bao nhiêu mỗi TCHP?"
    full_time = "I. Đại học chính quy | Tài chính - Ngân hàng: 600"
    part_time = "II. Hình thức vừa làm vừa học | Tài chính - Ngân hàng: 440"

    assert lexical_relevance_score(query, full_time) > lexical_relevance_score(
        query,
        part_time,
    )


def test_numeric_answer_detection_rejects_document_year_and_unit_heading() -> None:
    query = (
        "Theo QĐ 10232 về học phí năm học 2025-2026, Khoa học máy tính "
        "có mức bao nhiêu nghìn đồng mỗi TCHP?"
    )
    heading = (
        "Phụ lục năm học 2025-2026. Mức học phí mỗi TCHP được quy định "
        "theo đơn vị nghìn đồng."
    )

    assert not contains_requested_numeric_answer(query, heading)
    assert contains_requested_numeric_answer(
        query,
        "Khoa học máy tính, Kỹ thuật máy tính: 630",
    )


def test_numeric_answer_detection_rejects_unrelated_legal_dates() -> None:
    query = (
        "Theo QĐ 10232 năm học 2025-2026, học phí chương trình tiến sĩ "
        "là bao nhiêu mỗi năm?"
    )
    cover_page = (
        "Mức học phí các chương trình đào tạo. Căn cứ Luật Giáo dục đại học "
        "ngày 18 tháng 06 năm 2012 và Nghị định số 99/2019/NĐ-CP."
    )

    assert not contains_requested_numeric_answer(query, cover_page)
    assert contains_requested_numeric_answer(query, "Tiến sĩ: 26 triệu đồng/năm")


def test_lexical_fallback_zeroes_heading_without_requested_number() -> None:
    query = "Học phí Khoa học máy tính bao nhiêu nghìn đồng mỗi TCHP?"
    reranker = LexicalFallbackReranker("fallback")

    scores = reranker.rerank_batch(
        query,
        [
            _candidate("heading", "Mức học phí theo đơn vị nghìn đồng/TCHP"),
            _candidate("answer", "Khoa học máy tính: 630"),
        ],
    )

    assert scores[0] == 0.0
    assert scores[1] > 0.0
