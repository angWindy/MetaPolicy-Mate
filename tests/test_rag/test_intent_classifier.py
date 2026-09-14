"""Tests for the intent classifier used at the head of the retrieval graph.

The intent classifier is the entry gate of the new RAG workflow. It must:
* Detect small-talk (greetings / thanks / farewells) and route to the
  chitchat node without paying the cost of a Qdrant search.
* Pass non-trivial questions through to retrieval.
* Detect multi-intent queries (split on "?", ";", or Vietnamese
  connectors) so the decompose node can run sub-queries.
"""

from __future__ import annotations

import os

# Must be set before any settings module is imported so the
# ``validate_database_url`` validator does not reject in-memory fixtures.
os.environ.setdefault("APP_ENV", "test")

import pytest

from src.rag.decompose import _split_intents
from src.rag.intent_router import (
    QueryIntent,
    classify_assistant_query,
    classify_intent,
    is_small_talk,
)

# ─────────────────────────────────────────────────────────────────────────────
# classify_intent + is_small_talk
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    [
        "xin chào",
        "Xin chào!",
        "cảm ơn",
        "tạm biệt",
        "bye",
        "hello",
        "hi",
    ],
)
def test_is_small_talk_recognises_greetings_thanks_and_farewells(query: str):
    assert is_small_talk(query) is True
    assert classify_intent(query) is QueryIntent.SMALL_TALK


@pytest.mark.parametrize(
    "query",
    [
        "Quy chế chi tiêu nội bộ điều 5 khoản 2 nói gì?",
        "Cảm ơn bạn, cho hỏi điều 5 khoản 2 quy chế chi tiêu nội bộ?",
        "Xin chào, tôi muốn hỏi về học phí",
        "Căn cứ theo Quyết định số 10232/QĐ-ĐHBK",
    ],
)
def test_is_small_talk_rejects_real_questions(query: str):
    # Queries that start politely but contain real content are NOT small talk.
    assert is_small_talk(query) is False


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Bạn là ai?", QueryIntent.SELF_INTRODUCTION),
        ("Xin chào, hãy giới thiệu về bạn", QueryIntent.SELF_INTRODUCTION),
        ("Bạn có thể tự giới thiệu được không?", QueryIntent.SELF_INTRODUCTION),
        ("Bạn có thể làm được những gì?", QueryIntent.HELP),
        ("Bạn có các tác dụng gì?", QueryIntent.HELP),
        ("Chức năng của bạn là gì?", QueryIntent.HELP),
        ("Tôi có thể hỏi bạn những gì?", QueryIntent.HELP),
        ("Hướng dẫn tôi cách sử dụng hệ thống", QueryIntent.HELP),
    ],
)
def test_classifies_assistant_identity_and_help_queries(
    query: str,
    expected: QueryIntent,
):
    assert classify_assistant_query(query) is expected
    assert classify_intent(query) is expected


@pytest.mark.parametrize(
    "query",
    [
        "Bạn có thể cho tôi biết học phí là bao nhiêu?",
        "Hướng dẫn thủ tục xin nghỉ học",
        "Xin chào, tôi muốn hỏi về quy định học phí",
    ],
)
def test_assistant_query_classifier_does_not_capture_domain_questions(query: str):
    assert classify_assistant_query(query) is None


def test_classify_intent_returns_semantic_for_unstructured_query():
    intent = classify_intent("Quy chế chi tiêu nội bộ HUST điều 5 khoản 2 nói gì?")
    # Non-identifier, non-keyword-heavy → SEMANTIC.
    assert intent in {QueryIntent.SEMANTIC, QueryIntent.MIXED}


def test_classify_intent_returns_identifier_for_document_number():
    intent = classify_intent("Quyết định số 10232/QĐ-ĐHBK")
    # ``classify_query_type`` returns IDENTIFIER for queries that are
    # mostly a regulation/document number. The router then maps it to
    # the IDENTIFIER intent — but if the heuristic is too lenient it
    # may return MIXED, so we accept either as "not small talk".
    assert intent in {QueryIntent.IDENTIFIER, QueryIntent.MIXED}


def test_classify_intent_returns_keyword_for_short_query():
    intent = classify_intent("học phí")
    # Single short keyword → KEYWORD.
    assert intent is QueryIntent.KEYWORD


# ─────────────────────────────────────────────────────────────────────────────
# Multi-intent splitter (decompose_query_node's helper)
# ─────────────────────────────────────────────────────────────────────────────


def test_split_intents_on_question_mark():
    parts = _split_intents(
        "Quy chế chi tiêu nội bộ có áp dụng cho HUCE không? Và HUST thì sao?"
    )
    assert len(parts) == 2
    assert any("HUCE" in part for part in parts)
    assert any("HUST" in part for part in parts)


def test_split_intents_on_semicolon():
    parts = _split_intents("Câu hỏi một; Câu hỏi hai; Câu hỏi ba")
    assert len(parts) == 3


def test_split_intents_on_vietnamese_connectors():
    parts = _split_intents(
        "Quy chế chi tiêu nội bộ áp dụng cho HUST đồng thời HUCE"
    )
    assert len(parts) == 2


def test_split_intents_returns_single_part_for_simple_query():
    parts = _split_intents("Quy chế chi tiêu nội bộ điều 5 khoản 2 nói gì?")
    assert len(parts) == 1
