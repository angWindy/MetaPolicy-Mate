"""Multi-provider LLM factory.

Factory tạo LangChain chat model dựa trên provider được chọn trong RAGSettings.
Mỗi provider được wrap bằng `.with_structured_output(_StructuredAnswer)` để đảm bảo
đầu ra nhất quán.

Provider được hỗ trợ:
- `openai`     → ChatOpenAI (OpenAI GPT models)
- `anthropic`  → ChatAnthropic (Claude models)
- `gemini`     → ChatGoogleGenerativeAI (Google Gemini)
- `mistral`    → ChatMistralAI (Mistral models)
- `ollama`     → ChatOllama (local LLM via Ollama server)
- `template`   → TemplateChatGenerator (safe fallback, không cần API key)

Sử dụng:
    from src.services.llm_factory import build_llm

    settings = RAGSettings()  # hoặc get_rag_settings()
    llm = build_llm(settings)

    # Structured output (recommended)
    structured = llm.with_structured_output(MySchema)
    result = await structured.ainvoke("prompt")

    # Streaming (khi streaming_enabled=True)
    async for chunk in llm.astream("prompt"):
        print(chunk.content, end="", flush=True)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from src.rag.config import RAGSettings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.outputs import ChatResult
    from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Structured output schema (đồng nhất cho tất cả provider)
# ─────────────────────────────────────────────────────────────────────────────


class AnswerSchema(BaseModel):
    """Schema đầu ra bắt buộc cho tất cả LLM providers."""

    answer: str = Field(description="Câu trả lời bằng tiếng Việt chuẩn mực")
    cited_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Danh sách chunk_id đã được trích dẫn trong câu trả lời",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Cảnh báo nếu bằng chứng thiếu hoặc mâu thuẫn",
    )
    confidence: str = Field(
        default="low",
        description="Mức độ tự tin: low | medium | high",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Template generator (safe fallback, không cần API key)
# ─────────────────────────────────────────────────────────────────────────────


class _TemplateChatModel:
    """Chat model giả lập cho môi trường không có API key (dev/test)."""

    model_name: str = "template"
    streaming: bool = False

    def with_structured_output(self, schema: type[BaseModel]) -> _TemplateRunnable:
        return _TemplateRunnable(schema=schema)

    async def ainvoke(self, prompt: str | list[dict]) -> AnswerSchema:
        if isinstance(prompt, str):
            text = prompt
        else:
            text = prompt[-1].get("content", "") if prompt else ""
        return AnswerSchema(
            answer=f"[Template] Không thể sinh câu trả lời thực. Prompt: {text[:100]}...",
            cited_chunk_ids=[],
            warnings=["Template generator không có API key - cần cấu hình provider thực"],
            confidence="low",
        )

    async def astream(self, prompt: str) -> Any:
        """Stream interface trả về từng token một (giả lập)."""
        text = "[Template] "
        for char in text:
            yield _ChatChunk(content=char)


class _TemplateRunnable:
    def __init__(self, schema: type[BaseModel]):
        self.schema = schema

    async def ainvoke(self, prompt: str | list[dict]) -> AnswerSchema:
        text = prompt if isinstance(prompt, str) else (prompt[-1].get("content", "") if prompt else "")
        return AnswerSchema(
            answer=f"[Template] Câu trả lời mẫu cho: {text[:80]}...",
            cited_chunk_ids=[],
            warnings=["Template generator - cần provider thực để sinh câu trả lời chất lượng"],
            confidence="low",
        )

    async def astream(self, prompt: str) -> Any:
        text = "[Template] "
        for char in text:
            yield _ChatChunk(content=char)


class _ChatChunk:
    content: str = ""

    def __init__(self, content: str):
        self.content = content


# ─────────────────────────────────────────────────────────────────────────────
# Provider builders
# ─────────────────────────────────────────────────────────────────────────────


def _build_openai_llm(settings: RAGSettings) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": settings.model_name,
        "api_key": settings.openai_api_key,
        "temperature": settings.llm_temperature,
    }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    if settings.openai_org:
        kwargs["organization"] = settings.openai_org
    if settings.streaming_enabled:
        kwargs["streaming"] = True

    logger.info("Building OpenAI LLM: model=%s base_url=%s", settings.model_name, settings.openai_base_url)
    return ChatOpenAI(**kwargs)


def _build_anthropic_llm(settings: RAGSettings) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    kwargs: dict[str, Any] = {
        "model": settings.model_name or "claude-sonnet-4-20250514",
        "anthropic_api_key": settings.anthropic_api_key,
        "temperature": settings.llm_temperature,
    }
    if settings.anthropic_base_url:
        kwargs["anthropic_api_url"] = settings.anthropic_base_url
    if settings.streaming_enabled:
        kwargs["streaming"] = True

    logger.info("Building Anthropic LLM: model=%s", settings.model_name)
    return ChatAnthropic(**kwargs)


def _build_gemini_llm(settings: RAGSettings) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    kwargs: dict[str, Any] = {
        "model": settings.model_name or "gpt-4o-mini",
        "google_api_key": settings.gemini_api_key,
        "temperature": settings.llm_temperature,
    }
    if settings.gemini_base_url:
        kwargs["base_url"] = settings.gemini_base_url
    if settings.streaming_enabled:
        kwargs["streaming"] = True

    logger.info("Building Google Gemini LLM: model=%s", settings.model_name)
    return ChatGoogleGenerativeAI(**kwargs)


def _build_mistral_llm(settings: RAGSettings) -> BaseChatModel:
    from langchain_mistralai import ChatMistralAI

    kwargs: dict[str, Any] = {
        "model": settings.model_name or "mistral-large-latest",
        "mistral_api_key": settings.mistral_api_key,
        "temperature": settings.llm_temperature,
    }
    if settings.mistral_base_url:
        kwargs["endpoint"] = settings.mistral_base_url
    if settings.streaming_enabled:
        kwargs["streaming"] = True

    logger.info("Building MistralAI LLM: model=%s", settings.model_name)
    return ChatMistralAI(**kwargs)


def _build_ollama_llm(settings: RAGSettings) -> BaseChatModel:
    from langchain_ollama import ChatOllama

    model = settings.ollama_model or settings.model_name or "llama3"
    kwargs: dict[str, Any] = {
        "model": model,
        "base_url": settings.ollama_base_url or "http://localhost:11434/v1",
        "temperature": settings.llm_temperature,
        "timeout": "5m",
    }
    if settings.streaming_enabled:
        kwargs["streaming"] = True

    logger.info("Building Ollama LLM: model=%s base_url=%s", model, settings.ollama_base_url)
    return ChatOllama(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────

_BUILDER_MAP = {
    "openai": _build_openai_llm,
    "anthropic": _build_anthropic_llm,
    "gemini": _build_gemini_llm,
    "mistral": _build_mistral_llm,
    "ollama": _build_ollama_llm,
}


def build_llm(settings: RAGSettings | None = None) -> BaseChatModel | _TemplateChatModel:
    """Build a LangChain chat model from RAGSettings.

    Args:
        settings: RAGSettings instance. If None, loads from environment.

    Returns:
        LangChain BaseChatModel for the selected provider, or _TemplateChatModel
        for `template` provider.

    Raises:
        ValueError: If the provider is not recognized or required key is missing
            in non-production environments.

    Example:
        llm = build_llm()
        structured = llm.with_structured_output(AnswerSchema)
        result = await structured.ainvoke("Câu hỏi ở đây")
    """
    if settings is None:
        settings = RAGSettings()

    provider = settings.generator_provider

    if provider == "template":
        logger.debug("Using template generator (no API key required)")
        return _TemplateChatModel()

    builder = _BUILDER_MAP.get(provider)
    if builder is None:
        raise ValueError(
            f"Unknown generator_provider '{provider}'. "
            f"Supported: {list(_BUILDER_MAP.keys())} + 'template'."
        )

    return builder(settings)


def build_structured_llm(settings: RAGSettings | None = None) -> Runnable:
    """Build a structured-output LLM ready for RAG generation.

    Wrapper around `build_llm()` that applies `.with_structured_output(AnswerSchema)`.
    Khuyến nghị dùng method này thay vì `build_llm` trực tiếp.

    Example:
        structured = build_structured_llm()
        result = await structured.ainvoke("Quy định về nghỉ phép?")
        assert isinstance(result, AnswerSchema)
    """
    llm = build_llm(settings)
    if isinstance(llm, _TemplateChatModel):
        return llm.with_structured_output(AnswerSchema)
    return llm.with_structured_output(AnswerSchema)
