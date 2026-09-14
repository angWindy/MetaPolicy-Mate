"""Legacy LLM wrapper — delegates to the multi-provider factory.

DEPRECATED: Import from `src.services.llm_factory` directly for new code.
This module exists for backward compatibility with existing code paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.llm_factory import build_llm

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


def get_llm() -> BaseChatModel:
    """Build LLM using RAGSettings (multi-provider aware).

    DEPRECATED: Use `build_llm()` from `src.services.llm_factory` directly.
    """
    from src.rag.config import get_rag_settings

    settings = get_rag_settings()
    return build_llm(settings)
