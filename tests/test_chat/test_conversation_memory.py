from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from src.application.features.chat.ask.conversation_memory import (
    build_conversation_memory,
    is_context_dependent_follow_up,
)
from src.domain.entities.chat_turn import ChatTurn


def _turn(
    question: str,
    answer: str,
    *,
    document_number: str | None = "RAW-HUST-10232",
) -> ChatTurn:
    citations = (
        [{"document_number": document_number}] if document_number else []
    )
    return ChatTurn(
        id=uuid4(),
        session_id=uuid4(),
        question=question,
        answer=answer,
        citations=citations,
        created_at=datetime.now(UTC),
    )


def test_standalone_question_keeps_retrieval_query_clean():
    memory = build_conversation_memory(
        "Điểm A+ bắt đầu từ bao nhiêu?",
        [_turn("Học phí tiến sĩ bao nhiêu?", "26 triệu đồng/năm.")],
    )

    assert memory.retrieval_query == "Điểm A+ bắt đầu từ bao nhiêu?"
    assert "Học phí tiến sĩ" in memory.prompt_context
    assert memory.context_dependent is False


def test_follow_up_retrieval_uses_last_topic_and_document_not_old_answer():
    memory = build_conversation_memory(
        "Còn mức thạc sĩ thì sao?",
        [_turn("Học phí tiến sĩ bao nhiêu?", "26 triệu đồng/năm.")],
    )

    assert memory.context_dependent is True
    assert "Previous user topic: Học phí tiến sĩ bao nhiêu?" in (
        memory.retrieval_query
    )
    assert "Previously cited documents: RAW-HUST-10232" in (
        memory.retrieval_query
    )
    assert "26 triệu" not in memory.retrieval_query
    assert "26 triệu" in memory.prompt_context


def test_uncited_assistant_answer_is_not_remembered_as_evidence():
    memory = build_conversation_memory(
        "Vậy mức đó áp dụng khi nào?",
        [
            _turn(
                "Mức học phí là bao nhiêu?",
                "Một con số chưa được kiểm chứng.",
                document_number=None,
            )
        ],
    )

    assert "Một con số chưa được kiểm chứng" not in memory.prompt_context
    assert "Mức học phí là bao nhiêu?" in memory.prompt_context


def test_follow_up_cues_are_explicit_not_based_on_short_length_alone():
    assert is_context_dependent_follow_up("Còn mức thạc sĩ thì sao?")
    assert is_context_dependent_follow_up("Người này học ngành gì?")
    assert not is_context_dependent_follow_up("Học phí tiến sĩ bao nhiêu?")
