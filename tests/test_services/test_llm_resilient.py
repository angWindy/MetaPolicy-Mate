"""Tests for src/services/llm_resilient.py MultiProviderResilientLLM."""

from __future__ import annotations

import pytest

from src.rag.config import RAGSettings


class TestResilientLLMConfig:
    def test_llm_fallback_provider_list_parsed(self):
        s = RAGSettings(llm_fallback_providers="ollama,template")
        assert s.llm_fallback_provider_list == ["ollama", "template"]

    def test_llm_fallback_provider_list_empty(self):
        s = RAGSettings(llm_fallback_providers="")
        assert s.llm_fallback_provider_list == []

    def test_embedding_fallback_provider_list_parsed(self):
        s = RAGSettings(embedding_fallback_providers="sentence_transformers,hash")
        assert s.embedding_fallback_provider_list == ["sentence_transformers", "hash"]

    def test_default_retry_params(self):
        s = RAGSettings()
        assert s.llm_max_retries == 3
        assert s.llm_retry_base_delay == 2.0
        assert s.llm_retry_max_delay == 60.0
        assert s.embedding_max_retries == 3


class TestResilientLLMBuild:
    def test_resilient_llm_initializes_primary_only(self):
        """Template provider has no API key, should still init without error."""
        from src.services.llm_resilient import MultiProviderResilientLLM

        s = RAGSettings(
            generator_provider="template",
            llm_fallback_providers="template",
        )
        llm = MultiProviderResilientLLM(s)
        assert llm._primary_runnable is not None
        assert llm._fallback_runnables == []

    def test_resilient_llm_skips_duplicate_in_fallback_chain(self):
        """Primary provider should not appear in the fallback chain."""
        from src.services.llm_resilient import MultiProviderResilientLLM

        s = RAGSettings(
            generator_provider="template",
            llm_fallback_providers="template,ollama",
        )
        llm = MultiProviderResilientLLM(s)
        assert "template" not in llm._fallback_provider_names
        assert len(llm._fallback_runnables) == len(llm._fallback_provider_names)

    @pytest.mark.asyncio
    async def test_failed_fallback_build_does_not_misalign_provider_names(
        self,
        monkeypatch,
    ):
        """A missing optional provider must not break the remaining fallback."""
        from src.services.llm_factory import AnswerSchema
        from src.services.llm_resilient import MultiProviderResilientLLM

        original_builder = MultiProviderResilientLLM._build_llm_for_provider

        def build_available_only(self, provider_name):
            if provider_name == "ollama":
                raise ImportError("optional ollama package is not installed")
            return original_builder(self, provider_name)

        monkeypatch.setattr(
            MultiProviderResilientLLM,
            "_build_llm_for_provider",
            build_available_only,
        )
        settings = RAGSettings(
            generator_provider="openai",
            openai_api_key="test-key",
            llm_fallback_providers="ollama,template",
            llm_max_retries=1,
        )
        resilient = MultiProviderResilientLLM(settings)
        resilient._primary_runnable = None

        result = await resilient.ainvoke("test prompt")

        assert isinstance(result, AnswerSchema)
        assert resilient._fallback_provider_names == ["template"]
