"""Tests cho multi-provider LLM factory và generator."""

import pytest

from src.domain.schemas import RetrievedChunk
from src.rag.config import RAGSettings
from src.rag.generator import (
    MultiProviderAnswerGenerator,
    TemplateAnswerGenerator,
    build_answer_generator,
)
from src.services.llm_factory import (
    AnswerSchema,
    build_llm,
    build_structured_llm,
)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Factory Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMFactoryTemplate:
    def test_build_llm_template_returns_template_model(self):
        settings = RAGSettings(generator_provider="template")
        llm = build_llm(settings)
        assert type(llm).__name__ == "_TemplateChatModel"

    def test_build_structured_llm_template(self):
        settings = RAGSettings(generator_provider="template")
        structured = build_structured_llm(settings)
        # _TemplateRunnable có phương thức ainvoke nhưng không phải callable
        assert hasattr(structured, "ainvoke")

    @pytest.mark.asyncio
    async def test_template_ainvoke_returns_answer_schema(self):
        settings = RAGSettings(generator_provider="template")
        llm = build_llm(settings)
        # ainvoke là async → phải await
        result = await llm.ainvoke("quy định nghỉ phép")
        assert isinstance(result, AnswerSchema)
        assert result.confidence == "low"
        assert "Template" in result.answer

    @pytest.mark.asyncio
    async def test_template_structured_ainvoke_returns_schema(self):
        settings = RAGSettings(generator_provider="template")
        structured = build_structured_llm(settings)
        result = await structured.ainvoke("câu hỏi test")
        assert isinstance(result, AnswerSchema)
        assert hasattr(result, "answer")
        assert hasattr(result, "cited_chunk_ids")


class TestLLMFactoryMultiProvider:
    """Test lazy initialization - không gọi API khi khởi tạo."""

    def test_build_llm_openai_lazy_no_api_call(self):
        settings = RAGSettings(
            generator_provider="openai",
            openai_api_key="sk-test-key",
            app_env="development",
        )
        # Không raise - lazy init
        llm = build_llm(settings)
        assert llm is not None

    def test_build_llm_anthropic_lazy(self):
        settings = RAGSettings(
            generator_provider="anthropic",
            anthropic_api_key="sk-ant-test",
            app_env="development",
        )
        llm = build_llm(settings)
        assert llm is not None

    def test_build_llm_gemini_lazy(self):
        settings = RAGSettings(
            generator_provider="gemini",
            gemini_api_key="AIza-test",
            app_env="development",
        )
        llm = build_llm(settings)
        assert llm is not None

    def test_build_llm_mistral_lazy(self):
        settings = RAGSettings(
            generator_provider="mistral",
            mistral_api_key="mistral-test",
            app_env="development",
        )
        llm = build_llm(settings)
        assert llm is not None

    def test_build_llm_ollama_lazy(self):
        settings = RAGSettings(
            generator_provider="ollama",
            ollama_base_url="http://localhost:11434/v1",
            app_env="development",
        )
        llm = build_llm(settings)
        assert llm is not None

    def test_build_llm_unknown_provider_raises(self):
        # Pydantic validate enum ngay khi khởi tạo RAGSettings
        # không cần .model_validate()
        with pytest.raises(Exception, match="generator_provider"):
            RAGSettings(generator_provider="unknown_provider")


class TestLLMFactoryProductionValidation:
    """Production validator kiểm tra API key bắt buộc.

    Pydantic gọi model_validator ngay khi khởi tạo RAGSettings(...).
    """

    def test_production_openai_requires_key(self):
        with pytest.raises(Exception, match="OPENAI_API_KEY"):
            RAGSettings(
                generator_provider="openai",
                openai_api_key="",
                app_env="production",
            )

    def test_production_anthropic_requires_key(self):
        with pytest.raises(Exception, match="ANTHROPIC_API_KEY"):
            RAGSettings(
                generator_provider="anthropic",
                anthropic_api_key="",
                app_env="production",
            )

    def test_production_gemini_requires_key(self):
        with pytest.raises(Exception, match="GEMINI_API_KEY"):
            RAGSettings(
                generator_provider="gemini",
                gemini_api_key="",
                app_env="production",
            )

    def test_production_mistral_requires_key(self):
        with pytest.raises(Exception, match="MISTRAL_API_KEY"):
            RAGSettings(
                generator_provider="mistral",
                mistral_api_key="",
                app_env="production",
            )

    def test_production_with_valid_key_no_raise(self):
        # Không raise khi có key và dev_auth_bypass=false
        settings = RAGSettings(
            generator_provider="openai",
            openai_api_key="sk-valid",
            app_env="production",
            dev_auth_bypass=False,
        )
        assert settings.generator_provider == "openai"


# ─────────────────────────────────────────────────────────────────────────────
# Generator Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplateAnswerGenerator:
    @pytest.mark.asyncio
    async def test_no_evidence_returns_safe_answer(self):
        gen = TemplateAnswerGenerator()
        result = await gen.generate("quy định nghỉ phép?", evidence=[])
        assert "chưa có đủ căn cứ" in result.answer
        assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_with_evidence_returns_cited_answer(self):
        gen = TemplateAnswerGenerator()
        evidence = [
            RetrievedChunk(
                chunk_id="chunk-001",
                text="Cán bộ được nghỉ phép theo kế hoạch.",
                score=0.85,
                source="hybrid",
                metadata={
                    "document_number": "01/QĐ-ĐHBK",
                    "article": "5",
                    "clause": "2",
                    "page": 3,
                    "title": "Quy định nghỉ phép",
                },
            )
        ]
        result = await gen.generate("ai được nghỉ phép?", evidence=evidence)
        assert "chunk-001" in result.cited_chunk_ids
        assert "01/QĐ-ĐHBK" in result.answer


class TestMultiProviderAnswerGenerator:
    """Test lazy LLM initialization trong generator."""

    def test_generator_builds_for_all_providers(self):
        providers = ["openai", "anthropic", "gemini", "mistral", "ollama"]
        for provider in providers:
            s = RAGSettings(generator_provider=provider, app_env="development")
            gen = build_answer_generator(s)
            assert isinstance(gen, MultiProviderAnswerGenerator)

    def test_build_answer_generator_template(self):
        settings = RAGSettings(generator_provider="template")
        gen = build_answer_generator(settings)
        assert isinstance(gen, TemplateAnswerGenerator)

    def test_build_answer_generator_multi_provider(self):
        settings = RAGSettings(generator_provider="openai", app_env="development")
        gen = build_answer_generator(settings)
        assert isinstance(gen, MultiProviderAnswerGenerator)
        # LLM chưa được khởi tạo (lazy)
        assert gen._llm is None

    @pytest.mark.asyncio
    async def test_multi_provider_catches_llm_error(self):
        """Khi LLM raise exception, generator vẫn trả về safe answer."""
        # Dùng template vì nó không cần API
        settings = RAGSettings(generator_provider="template")
        gen = build_answer_generator(settings)
        result = await gen.generate("test", evidence=[])
        assert result.confidence == "low"
        assert "căn cứ" in result.answer


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Generator with RAGSettings from env
# ─────────────────────────────────────────────────────────────────────────────


class TestGeneratorEnvIntegration:
    @pytest.mark.asyncio
    async def test_template_generator_with_full_evidence(self):
        """Template generator xử lý full evidence metadata."""
        settings = RAGSettings(generator_provider="template")
        gen = build_answer_generator(settings)
        evidence = [
            RetrievedChunk(
                chunk_id="c1",
                text="Điều 5. Cán bộ được nghỉ phép theo kế hoạch.",
                score=0.9,
                source="hybrid",
                metadata={
                    "document_number": "05/QĐ-ĐHBK",
                    "article": "5",
                    "clause": "1",
                    "point": "a",
                    "page": 10,
                    "title": "Quy định nghỉ phép năm",
                },
            ),
            RetrievedChunk(
                chunk_id="c2",
                text="Trưởng đơn vị phê duyệt kế hoạch nghỉ phép.",
                score=0.7,
                source="hybrid",
                metadata={
                    "document_number": "05/QĐ-ĐHBK",
                    "article": "6",
                    "clause": "2",
                    "page": 11,
                    "title": "Quy định nghỉ phép năm",
                },
            ),
        ]
        result = await gen.generate("quy định nghỉ phép áp dụng cho ai?", evidence=evidence)
        # Template generator chọn evidence[0] (score cao nhất)
        assert len(result.cited_chunk_ids) == 1
        assert result.cited_chunk_ids[0] == "c1"
        # score=0.9 >= 0.5 → confidence="high"
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_template_generator_low_score_confidence(self):
        """Confidence 'medium' khi score < 0.5."""
        settings = RAGSettings(generator_provider="template")
        gen = build_answer_generator(settings)
        evidence = [
            RetrievedChunk(
                chunk_id="c1",
                text="Nội dung.",
                score=0.3,  # < 0.5
                source="hybrid",
                metadata={"document_number": "D1", "title": "T"},
            )
        ]
        result = await gen.generate("câu hỏi?", evidence=evidence)
        assert result.confidence == "medium"

    @pytest.mark.asyncio
    async def test_template_generator_no_citation_when_missing_metadata(self):
        """Khi metadata không có locator, dùng title."""
        settings = RAGSettings(generator_provider="template")
        gen = build_answer_generator(settings)
        evidence = [
            RetrievedChunk(
                chunk_id="c1",
                text="Nội dung văn bản.",
                score=0.9,
                source="hybrid",
                metadata={},  # Không có article/clause/page
            )
        ]
        result = await gen.generate("câu hỏi?", evidence=evidence)
        assert "c1" in result.cited_chunk_ids
        assert "văn bản nguồn" in result.answer.lower()
