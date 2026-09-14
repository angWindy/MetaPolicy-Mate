import unicodedata

import pytest

from src.domain.schemas import QueryType
from src.retrieval.query_transform import (
    build_query_variants,
    classify_query_type,
    extract_alphanumeric_identifiers,
    extract_article_clause,
    extract_document_numbers,
    extract_form_codes,
    normalize_unicode,
    normalize_whitespace,
    validate_query,
)


def test_normalize_unicode_uses_nfc_without_removing_vietnamese_accents():
    decomposed = unicodedata.normalize("NFD", "Quyết định")
    normalized = normalize_unicode(decomposed)
    assert normalized == "Quyết định"
    assert unicodedata.is_normalized("NFC", normalized)


def test_normalize_whitespace_preserves_content_and_identifiers():
    assert normalize_whitespace("  Tra cứu\n\t QT-TC-003  ") == "Tra cứu QT-TC-003"


def test_extracts_document_number_without_modification():
    query = "Cho tôi xem Quyết định 123/QĐ-CT và 45/QĐ-ĐHBK."
    assert extract_document_numbers(query) == ["123/QĐ-CT", "45/QĐ-ĐHBK"]


@pytest.mark.parametrize(
    "query",
    [
        "Theo QĐ 5445, quy định này áp dụng thế nào?",
        "Quy chế 5445 yêu cầu nội dung gì?",
        "Quyết định số 5445 có hiệu lực khi nào?",
    ],
)
def test_extracts_bare_document_number_only_after_document_cue(query):
    assert extract_document_numbers(query) == ["5445"]


def test_does_not_treat_an_ordinary_number_as_a_document_reference():
    assert extract_document_numbers("Mức tối thiểu là 132 tín chỉ phải không?") == []


def test_extracts_form_code_without_confusing_document_number():
    query = "Biểu mẫu QT-TC-003 đi kèm 123/QĐ-CT"
    assert extract_form_codes(query) == ["QT-TC-003"]


def test_extracts_opaque_alphanumeric_identifier_without_years():
    query = "Mã số 20240799E thuộc ngành nào trong năm 2024?"

    assert extract_alphanumeric_identifiers(query) == ["20240799E"]


def test_student_code_is_classified_as_mixed_identifier_query():
    assert classify_query_type("Mã 20240799E học ngành gì?") == QueryType.MIXED


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Điều 5 khoản 2 quy định nội dung gì?", {"articles": ["5"], "clauses": ["2"]}),
        ("Dieu 7, khoan 3", {"articles": ["7"], "clauses": ["3"]}),
    ],
)
def test_extracts_article_and_clause_for_accented_and_unaccented_queries(query, expected):
    assert extract_article_clause(query) == expected


@pytest.mark.parametrize(
    ("query", "expected_type"),
    [
        ("QT-TC-003", QueryType.IDENTIFIER),
        ("Điều 5 khoản 2", QueryType.IDENTIFIER),
        ("học phí cao học", QueryType.KEYWORD),
        ("Sinh viên được nghỉ học trong trường hợp nào?", QueryType.SEMANTIC),
        ("Điều 5 của 123/QĐ-CT quy định gì?", QueryType.MIXED),
        (
            "Điều kiện nhận học bổng là gì và hồ sơ cần những gì?",
            QueryType.MULTI_INTENT,
        ),
    ],
)
def test_classifies_vietnamese_query_types(query, expected_type):
    assert classify_query_type(query) == expected_type


def test_query_variants_keep_original_and_protect_identifiers():
    query = "  Nội dung QT-TC-003 theo 123/QĐ-CT là gì?  "
    variants = build_query_variants(query)

    assert variants[0] == query
    assert len(variants) <= 3
    assert any("Noi dung" in variant for variant in variants)
    assert all("QT-TC-003" in variant for variant in variants)
    assert all("123/QĐ-CT" in variant for variant in variants)


def test_unaccented_query_is_not_rewritten_unnecessarily():
    query = "quy dinh hoc phi"
    assert build_query_variants(query) == [query]


@pytest.mark.parametrize("query", ["", "   ", "?!@#$%^&*()"])
def test_validate_query_rejects_empty_or_special_only_query(query):
    with pytest.raises(ValueError):
        validate_query(query)


def test_validate_query_rejects_query_over_safe_limit():
    with pytest.raises(ValueError, match="5000"):
        validate_query("a" * 5001)
