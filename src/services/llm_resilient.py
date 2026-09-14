"""Resilient LLM wrapper: retry + automatic provider fallback.

Architecture:
  MultiProviderResilientLLM wraps a primary structured LLM (from build_structured_llm)
  and maintains a fallback chain built from LLM_FALLBACK_PROVIDERS.

  Each ainvoke call:
  1. Tries primary with exponential backoff retry (LLM_MAX_RETRIES).
  2. If all retries exhausted, tries next fallback provider.
  3. Falls back through the chain in order.
  4. Last resort is always template (never raises — returns a safe answer).

Usage:
    resilient = MultiProviderResilientLLM(settings)
    result = await resilient.ainvoke("Câu hỏi ở đây")
    assert isinstance(result, AnswerSchema)
"""

from __future__ import annotations

import logging
from typing import Any

from src.rag.config import RAGSettings

if True:
    from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)


class MultiProviderResilientLLM:
    """LLM wrapper with exponential-backoff retry and automatic provider fallback.

    Falls back through the chain in order from LLM_FALLBACK_PROVIDERS.
    The last provider in the chain should be "template" (never fails, no API key needed).
    """

    def __init__(self, settings: RAGSettings):
        self._settings = settings
        self._primary_runnable: Runnable | None = None
        self._fallback_runnables: list[Runnable] = []
        self._fallback_provider_names: list[str] = []
        self._init_llm_chain()

    # ── Initialization ──────────────────────────────────────────────────────────

    def _init_llm_chain(self) -> None:
        from src.services.llm_factory import build_structured_llm

        # Primary LLM (from GENERATOR_PROVIDER)
        try:
            self._primary_runnable = build_structured_llm(self._settings)
            logger.info(
                "ResilientLLM: primary provider=%s",
                self._settings.generator_provider,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ResilientLLM: failed to build primary provider %s: %s. "
                "Will try fallbacks.",
                self._settings.generator_provider,
                exc,
            )
            self._primary_runnable = None

        # Fallback chain from LLM_FALLBACK_PROVIDERS
        # ``built_names`` keeps the providers that actually built successfully
        # so that ``ainvoke`` can zip names with runnables without raising
        # ``ValueError: zip() argument ... is shorter than argument ...``.
        built_names: list[str] = []
        for provider_name in self._settings.llm_fallback_provider_list:
            if provider_name == self._settings.generator_provider:
                # Don't re-add primary as fallback
                continue
            try:
                fallback_runnable = self._build_llm_for_provider(provider_name)
                self._fallback_runnables.append(fallback_runnable)
                self._fallback_provider_names.append(provider_name)
                built_names.append(provider_name)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "ResilientLLM: skipped fallback provider %s (build failed): %s",
                    provider_name,
                    exc,
                )
        if built_names:
            logger.info(
                "ResilientLLM: fallback chain built: %s",
                built_names,
            )

    def _build_llm_for_provider(self, provider_name: str) -> Runnable:
        """Build a structured LLM for a specific provider name."""
        from src.services.llm_factory import AnswerSchema

        # Clone settings with the target provider
        settings_override = self._settings.model_copy(deep=True)
        settings_override.generator_provider = provider_name  # type: ignore[assignment]

        llm = self._build_llm_impl(settings_override)
        return llm.with_structured_output(AnswerSchema)

    def _build_llm_impl(self, settings: RAGSettings):
        """Build a raw (non-structured) LLM for the given settings."""
        if settings.generator_provider == "template":
            from src.services.llm_factory import _TemplateChatModel

            return _TemplateChatModel()

        builder_map = {
            "openai": "_build_openai_llm",
            "anthropic": "_build_anthropic_llm",
            "gemini": "_build_gemini_llm",
            "mistral": "_build_mistral_llm",
            "ollama": "_build_ollama_llm",
        }
        from src.services import llm_factory as _lf

        builder_name = builder_map.get(settings.generator_provider)
        if builder_name is None:
            raise ValueError(f"Unknown provider: {settings.generator_provider}")

        builder = getattr(_lf, builder_name)
        return builder(settings)

    # ── Public interface ──────────────────────────────────────────────────────

    async def ainvoke(
        self, prompt: str | list[dict]
    ) -> Any:
        """Call the LLM with retry + fallback across the provider chain.

        Args:
            prompt: String or LangChain message list.

        Returns:
            AnswerSchema (or dict) from the first provider that succeeds.

        Raises:
            RuntimeError: only if even the template fallback fails (should never happen).
        """
        from src.services.retry_utils import is_retryable, with_retry

        # Collect all runnables in order: primary first, then fallbacks
        all_runnables: list[tuple[str, Runnable]] = []
        if self._primary_runnable is not None:
            all_runnables.append(
                (self._settings.generator_provider, self._primary_runnable)
            )
        # Use ONLY fallback providers that were successfully built.
        # Without this filter, zip(strict=True) below raises ValueError
        # when one of the configured fallbacks failed to build (e.g. ollama
        # unreachable → skipped, but still present in provider list).
        for provider_name, runnable in zip(
            self._fallback_provider_names,
            self._fallback_runnables,
            strict=True,
        ):
            all_runnables.append((provider_name, runnable))

        last_exc: Exception | None = None

        for provider_name, runnable in all_runnables:
            try:
                result = await with_retry(
                    _ainvoke,
                    runnable,
                    prompt,
                    max_attempts=self._settings.llm_max_retries,
                    base_delay=self._settings.llm_retry_base_delay,
                    max_delay=self._settings.llm_retry_max_delay,
                )
                logger.info(
                    "ResilientLLM: provider %s succeeded after retry",
                    provider_name,
                )
                return result
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if is_retryable(exc):
                    logger.warning(
                        "ResilientLLM: provider %s failed (retryable, will try fallback if available): %s",
                        provider_name,
                        exc,
                    )
                else:
                    logger.warning(
                        "ResilientLLM: provider %s failed (non-retryable, will try fallback if available): %s",
                        provider_name,
                        exc,
                    )
                # Continue to next provider in chain

        # Should never reach here because template is always the last fallback
        raise RuntimeError(
            f"ResilientLLM: all providers failed, including template fallback. "
            f"Last error: {last_exc}"
        ) from last_exc


async def _ainvoke(runnable: Runnable, prompt: str | list[dict]) -> Any:
    """Thin wrapper to make a LangChain runnable awaitable for with_retry."""
    return await runnable.ainvoke(prompt)
