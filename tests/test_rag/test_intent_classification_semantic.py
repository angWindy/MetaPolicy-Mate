"""Tests for the extended semantic intent types (Phase B).

After Phase A+B, ``classify_intent`` distinguishes nine semantic query
types in addition to the original small-talk / multi-intent / identifier
/ keyword / semantic / mixed intents. These tests verify the routing
logic for each new intent.
"""

from __future__ import annotations

import os

# Must be set before any settings module is imported so the
# ``validate_database_url`` validator does not reject in-memory fixtures.
os.environ.setdefault("APP_ENV", "test")

import pytest

from src.rag.intent_router import (
    QueryIntent,
    classify_intent,
    classify_semantic_intent,
    _is_out_of_scope,
)


# ─────────────────────────────────────────────────────────────────────────────
# Semantic intent (the lower tier; 9 new types)
# ─────────────────────────────────────────────────────────────────────────────


def test_semantic_intent_detects_procedure():
    intent = classify_semantic_intent("Quy trình xin nghỉ phép như thế nào?")
    assert intent is QueryIntent.PROCEDURE


def test_semantic_intent_detects_comparison():
    intent = classify_semantic_intent("So sánh chế độ nghỉ phép của giảng viên và nhân viên")
    assert intent is QueryIntent.COMPARISON


def test_semantic_intent_detects_condition_lookup():
    intent = classify_semantic_intent("Điều kiện để được nghỉ phép năm là gì?")
    assert intent is QueryIntent.CONDITION_LOOKUP


def test_semantic_intent_detects_form_generation():
    intent = classify_semantic_intent("Tôi muốn tạo đơn xin nghỉ phép")
    assert intent is QueryIntent.FORM_GENERATION


def test_semantic_intent_detects_form_info():
    intent = classify_semantic_intent("Mẫu đơn xin nghỉ phép ở đâu?")
    assert intent is QueryIntent.FORM_INFO


def test_semantic_intent_detects_follow_up():
    intent = classify_semantic_intent("Cho biết thêm chi tiết về điều 5")
    assert intent is QueryIntent.FOLLOW_UP


def test_semantic_intent_detects_information_policy():
    intent = classify_semantic_intent("Quy định về nghỉ phép áp dụng cho cán bộ")
    assert intent is QueryIntent.INFORMATION_POLICY


def test_semantic_intent_defaults_to_semantic():
    # No keyword match → falls back to SEMANTIC.
    intent = classify_semantic_intent("nội dung của văn bản 10232")
    assert intent is QueryIntent.SEMANTIC


# ─────────────────────────────────────────────────────────────────────────────
# classify_intent — top-level routing including the new semantic types
# ─────────────────────────────────────────────────────────────────────────────


def test_classify_intent_returns_out_of_scope_for_unrelated_topic():
    intent = classify_intent("Tin tức bóng đá hôm nay")
    assert intent is QueryIntent.OUT_OF_SCOPE


def test_classify_intent_returns_ambiguous_for_deictic_reference():
    intent = classify_intent("nó")
    assert intent is QueryIntent.AMBIGUOUS


def test_classify_intent_returns_form_info_for_form_question():
    intent = classify_intent("Tôi cần tải mẫu đơn xin thôi học")
    # Form-info keywords ("mẫu", "tải") trigger FORM_INFO before semantic
    # intent classification.
    assert intent is QueryIntent.FORM_INFO


def test_classify_intent_returns_form_generation_for_creation_request():
    intent = classify_intent("Làm đơn xin nghỉ phép giúp tôi")
    assert intent is QueryIntent.FORM_GENERATION


def test_classify_intent_routes_procedure_through_semantic():
    # The top-level classify_intent routes everything that isn't
    # small-talk / out-of-scope / multi-intent through ``SEMANTIC`` when
    # the query isn't identifier/keyword/mixed. The semantic type is
    # stored as metadata for downstream nodes to inspect.
    intent = classify_intent("Các bước thực hiện quy trình đăng ký tín chỉ")
    assert intent is QueryIntent.PROCEDURE


# ─────────────────────────────────────────────────────────────────────────────
# Out-of-scope helper
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "dịch thuật câu này sang tiếng Anh",
        "lập trình python như thế nào",
        "tính toán phương trình bậc 2",
    ],
)
def test_is_out_of_scope_for_non_policy_queries(query: str):
    assert _is_out_of_scope(query) is True


@pytest.mark.parametrize(
    "query",
    [
        "Quy định nghỉ phép áp dụng cho ai?",
        "Quy chế đào tạo tín chỉ HUST điều 5",
    ],
)
def test_is_out_of_scope_false_for_policy_queries(query: str):
    assert _is_out_of_scope(query) is False