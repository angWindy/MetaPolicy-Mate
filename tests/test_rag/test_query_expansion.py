
from src.retrieval.query_expansion import build_lexical_query, expand_query


def test_expansion_does_not_drop_original_query():
    q = "Chứng chỉ JLPT N5 tương ứng bậc CEFR nào?"
    extras = expand_query(q)
    assert q not in extras  # expansion is additions only
    assert "quy đổi tương đương các chứng chỉ tiếng Nhật" in extras
    assert "JLPT CEFR-VN" in extras


def test_expansion_handles_ielts_pfiev():
    q = "IELTS đầu khóa PFIEV"
    extras = expand_query(q)
    assert any("Bảng quy đổi tương đương các chứng chỉ tiếng Anh" in e for e in extras)
    assert any("CTĐT Việt-Pháp PFIEV" in e for e in extras)


def test_expansion_preserves_document_number_identifier():
    q = "Quyết định 7737/QĐ-ĐHBK do ai ký?"
    extras = expand_query(q)
    # Identifier preserved verbatim.
    assert any("7737/QĐ-ĐHBK" in e for e in extras)
    # Signature appendix vocabulary surfaced.
    assert "PHÓ GIÁM ĐỐC" in extras or "GIÁM ĐỐC" in extras


def test_expansion_handles_dieu_khoan_reversed():
    q = "Khoản 2 Điều 18 của Quy chế đào tạo được áp dụng từ khóa nào?"
    extras = expand_query(q)
    assert any("Điều 18 khoản 2" in e for e in extras)


def test_expansion_caps_at_max_extra():
    q = "Mức học phí Tiến sĩ toàn khóa là bao nhiêu?"
    extras = expand_query(q, max_extra=2)
    assert len(extras) <= 2


def test_expansion_no_match_returns_empty():
    q = "đây là một câu hỏi chung chung không match rule nào"
    extras = expand_query(q)
    assert extras == []


def test_lexical_query_activates_tuition_expansion_without_dropping_question():
    question = "Theo bảng học phí sau đại học, Tiến sĩ thu hằng năm bao nhiêu?"

    query = build_lexical_query(question)

    assert query.startswith(question)
    assert "Mức học phí chương trình đào tạo" in query
    assert "Tiến sĩ đồng/năm" in query


def test_lexical_query_adds_grade_table_headers():
    query = build_lexical_query("Bao nhiêu điểm theo thang 10 mới được A+?")

    assert "điểm chữ quy đổi" in query.casefold()


def test_expansion_bridges_course_pass_threshold_vocabulary():
    extras = expand_query(
        "Học phần thông thường và đồ án tốt nghiệp cần tối thiểu điểm chữ nào để đạt?"
    )

    assert any("từ điểm D" in item and "từ C" in item for item in extras)


def test_expansion_bridges_credit_registration_heading():
    extras = expand_query(
        "Giới hạn tín chỉ đăng ký ở học kỳ chính và học kỳ hè là gì?"
    )

    assert any("Số lượng TC đăng ký" in item for item in extras)


def test_expansion_bridges_final_exam_component_vocabulary():
    extras = expand_query(
        "Trọng số điểm thi kết thúc học phần chiếm tối thiểu bao nhiêu phần trăm?"
    )

    assert any("điểm cuối kỳ" in item for item in extras)


def test_expansion_prefers_standard_program_graduation_english_row():
    extras = expand_query(
        "Chuẩn tiếng Anh đầu ra xét tốt nghiệp yêu cầu tối thiểu bậc mấy?"
    )

    assert any("CTĐT chuẩn" in item for item in extras)


def test_expansion_bridges_chemical_engineering_abbreviation():
    extras = expand_query("Học phí Kỹ thuật hóa học là bao nhiêu?")

    assert "KT hóa học" in extras
