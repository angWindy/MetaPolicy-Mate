"""Tests for citation validation in answer generators.

Regression: An LLM (or a corrupted response) can include chunk_ids that were
not in the evidence provided. The generator must defensively drop these
hallucinated citations and surface a warning.
"""

from __future__ import annotations

import pytest

from src.domain.schemas import RetrievedChunk
from src.rag.generator import (
    TemplateAnswerGenerator,
    _validate_citations,
)
from src.services.llm_factory import AnswerSchema


def _chunk(chunk_id: str, text: str = "...", **metadata) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=0.8,
        source="keyword",
        metadata=metadata or {"document_number": "QĐ-001"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# _validate_citations unit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_validate_citations_keeps_allowed_ids():
    validated, dropped = _validate_citations(
        ["a", "b", "c"], allowed_ids={"a", "b", "c"}
    )
    assert validated == ["a", "b", "c"]
    assert dropped == []


def test_validate_citations_drops_unknown_ids():
    validated, dropped = _validate_citations(
        ["a", "fake-id", "b"], allowed_ids={"a", "b"}
    )
    assert validated == ["a", "b"]
    assert dropped == ["fake-id"]


def test_validate_citations_deduplicates():
    validated, dropped = _validate_citations(
        ["a", "a", "b", "b"], allowed_ids={"a", "b"}
    )
    assert validated == ["a", "b"]
    assert dropped == []


def test_validate_citations_handles_empty_lists():
    validated, dropped = _validate_citations([], allowed_ids={"a"})
    assert validated == []
    assert dropped == []


def test_validate_citations_preserves_order():
    """First-seen order is preserved (so cite [3] appears before [1])."""
    validated, _ = _validate_citations(
        ["c", "a", "b"], allowed_ids={"a", "b", "c"}
    )
    assert validated == ["c", "a", "b"]


# ─────────────────────────────────────────────────────────────────────────────
# TemplateAnswerGenerator tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_template_generator_with_evidence():
    """TemplateAnswerGenerator returns a citation pointing to evidence chunk."""
    generator = TemplateAnswerGenerator()
    chunks = [_chunk("chunk-1", "Học phí năm 2025 là 20 triệu", document_number="QĐ-10232", page=1)]

    result = await generator.generate("Học phí bao nhiêu?", chunks)

    assert "QĐ-10232" in result.answer
    assert "chunk-1" in result.cited_chunk_ids
    assert result.confidence in {"low", "medium", "high"}


@pytest.mark.asyncio
async def test_template_generator_handles_missing_metadata():
    """If evidence metadata is incomplete, generator must not produce 'None' citations.

    Regression: Previously, missing metadata produced citations like
    'QĐ-001, Điều None, trang None' which were meaningless.
    """
    generator = TemplateAnswerGenerator()
    # chunk with incomplete metadata (no article, no clause, no page)
    chunks = [_chunk("chunk-x", "Some text", document_number="QĐ-XYZ")]

    result = await generator.generate("Test query", chunks)

    # The answer must not contain literal 'None' as a citation
    assert "None" not in result.answer
    assert "QĐ-XYZ" in result.answer


@pytest.mark.asyncio
async def test_template_generator_no_evidence_returns_safe_answer():
    """No evidence → safe low-confidence answer with no citations."""
    generator = TemplateAnswerGenerator()
    result = await generator.generate("Test query", [])

    assert result.confidence == "low"
    assert result.cited_chunk_ids == []
    assert "chưa có đủ căn cứ" in result.answer.lower() or "chưa" in result.answer.lower()


# ─────────────────────────────────────────────────────────────────────────────
# MultiProviderAnswerGenerator hallucinated citation test
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_multiprovider_generator_drops_hallucinated_citations(monkeypatch):
    """When LLM returns citations not in evidence, they must be dropped.

    This is a critical defense against hallucinated citations leaking
    into the user-facing answer.
    """
    from src.rag.config import RAGSettings
    from src.rag.generator import MultiProviderAnswerGenerator

    settings = RAGSettings(
        generator_provider="template",  # will be overridden in mock
        generator_model="test-model",
    )
    generator = MultiProviderAnswerGenerator(settings)

    # Mock the resilient LLM to return an AnswerSchema with hallucinated IDs
    class MockLLM:
        async def ainvoke(self, prompt):
            return AnswerSchema(
                answer="Theo tài liệu...",
                cited_chunk_ids=["real-chunk", "fake-chunk-1", "fake-chunk-2"],
                warnings=[],
                confidence="high",
            )

    generator._llm = MockLLM()

    evidence = [_chunk("real-chunk", "Real evidence", document_number="QĐ-001")]

    result = await generator.generate("Test query", evidence)

    # Only the real chunk_id should be cited
    assert result.cited_chunk_ids == ["real-chunk"]
    # Warning must surface the dropped IDs
    assert any("fake-chunk" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_multiprovider_generator_handles_dict_response_with_bad_citations(monkeypatch):
    """Dict response (from non-Pydantic LLM) with hallucinated IDs must also be filtered."""
    from src.rag.config import RAGSettings
    from src.rag.generator import MultiProviderAnswerGenerator

    settings = RAGSettings(
        generator_provider="template",
        generator_model="test-model",
    )
    generator = MultiProviderAnswerGenerator(settings)

    class MockLLM:
        async def ainvoke(self, prompt):
            return {
                "answer": "Some answer",
                "cited_chunk_ids": ["good-id", "hallucinated-id"],
                "warnings": [],
                "confidence": "high",
            }

    generator._llm = MockLLM()
    evidence = [_chunk("good-id", "text", document_number="QĐ-001")]

    result = await generator.generate("Test query", evidence)

    assert result.cited_chunk_ids == ["good-id"]
    assert any("hallucinated-id" in w for w in result.warnings)


def test_system_prompt_treats_history_as_context_not_evidence():
    from src.rag.config import RAGSettings

    prompt = RAGSettings().system_prompt_template

    assert "CONVERSATION CONTEXT" in prompt
    assert "NOT factual evidence" in prompt
    assert "exact sentence or table row" in prompt


@pytest.mark.asyncio
async def test_generator_focuses_long_table_evidence_on_requested_row():
    from src.rag.config import RAGSettings
    from src.rag.generator import MultiProviderAnswerGenerator

    settings = RAGSettings(
        generator_provider="template",
        generator_model="test-model",
    )
    generator = MultiProviderAnswerGenerator(settings)

    class CapturingLLM:
        prompt = ""

        async def ainvoke(self, prompt):
            self.prompt = prompt
            return AnswerSchema(
                answer="Hoàng Văn Mạnh học Kỹ thuật vật liệu [1].",
                cited_chunk_ids=["table-chunk"],
                warnings=[],
                confidence="high",
            )

    llm = CapturingLLM()
    generator._llm = llm
    rows = [
        "| TT | Họ và tên | Mã học viên | Ngành |",
        "|---|---|---|---|",
        *[
            f"| {index} | Sinh viên {index} | 20240{index:03d}E | Cơ khí |"
            for index in range(1, 80)
        ],
        "| 80 | Hoàng Văn Mạnh | 20240799E | Kỹ thuật vật liệu |",
    ]
    evidence = [
        _chunk(
            "table-chunk",
            "\n".join(rows),
            document_number="RAW-HUST-10714-table",
        )
    ]

    await generator.generate("Mã 20240799E là ai?", evidence)

    assert "Hoàng Văn Mạnh" in llm.prompt
    assert "20240799E" in llm.prompt
    assert "Sinh viên 1 |" not in llm.prompt
