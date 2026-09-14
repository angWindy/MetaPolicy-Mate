"""Retry utilities with exponential backoff for external API calls.

Retry policy:
1. Catch known transient errors (rate limits, timeouts, 5xx).
2. Sleep with exponential backoff + jitter between retries.
3. After max retries exhausted, surface the last exception.

Fallback providers:
- LLM: primary (Gemini/OpenAI/etc) → Ollama (local) → Template (no-key safe fallback)
- Embedding: primary (Gemini/OpenAI) → sentence_transformers (local) → Hash (deterministic)

Usage:
    from src.services.retry_utils import with_retry, RETRYABLE_EXC_TYPES

    @with_retry(max_attempts=3, base_delay=1.0)
    async def call_api():
        return await client.ainvoke(...)
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ─────────────────────────────────────────────────────────────────────────────
# Exception classification
# ─────────────────────────────────────────────────────────────────────────────

_RETRYABLE_MSG_SUBSTRINGS = (
    "rate limit",
    "rate_limit",
    "429",
    "503",
    "502",
    "500",
    "timeout",
    "timed out",
    "temporarily unavailable",
    "quota",
    "throttl",
    "overloaded",
    "too many requests",
    "service unavailable",
    "internal server error",
)


def is_retryable(exc: BaseException) -> bool:
    """Return True if the exception is a transient/retryable error."""
    msg = str(exc).lower()
    return any(needle in msg for needle in _RETRYABLE_MSG_SUBSTRINGS)


def is_rate_limit(exc: BaseException) -> bool:
    """Return True if the exception is specifically a rate-limit (RPM/TPM)."""
    msg = str(exc).lower()
    return any(
        needle in msg
        for needle in ("rate limit", "rate_limit", "429", "quota", "too many requests", "throttl")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Backoff calculation
# ─────────────────────────────────────────────────────────────────────────────

def _jitter(delay: float) -> float:
    """Add ±20% jitter to prevent thundering herd."""
    return delay * (0.8 + random.random() * 0.4)


def backoff_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Exponential backoff: base * 2^attempt, capped at max_delay.

    | attempt | base=1.0 | max=60 |
    |---------|----------|-------|
    | 0       | 0.8-1.2 | 0.8-1.2 |
    | 1       | 1.6-2.4 | 1.6-2.4 |
    | 2       | 3.2-4.8 | 3.2-4.8 |
    | 3       | 6.4-9.6 | 6.4-9.6 |
    | 4       | 12.8-19 | 12.8-19 |
    | 5       | 25.6-38 | 25.6-38 |
    | 6       | 51.2-76 | 51.2-60  |
    """
    raw = base_delay * (2**attempt)
    capped = min(raw, max_delay)
    return _jitter(capped)


# ─────────────────────────────────────────────────────────────────────────────
# Core retry function
# ─────────────────────────────────────────────────────────────────────────────

RetriableFn = Callable[..., Awaitable[T]]


async def with_retry(
    fn: RetriableFn[T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_only: bool = True,
    on_retry: Callable[[int, BaseException], None] | None = None,
    **kwargs: Any,
) -> T:
    """Call an async function with exponential-backoff retry on transient errors.

    Args:
        fn: Async callable to execute.
        *args: Positional arguments forwarded to fn.
        max_attempts: Maximum call attempts (1 = no retry).
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Cap the delay at this value.
        retryable_only: If True, only retry when `is_retryable(e)` is True;
            otherwise retry on every exception.
        on_retry: Optional callback(attempt, exception) called before each retry.
        **kwargs: Keyword arguments forwarded to fn.

    Returns:
        The return value of fn on the first successful call.

    Raises:
        The last exception if all attempts are exhausted.

    Example:
        result = await with_retry(
            my_llm.ainvoke,
            prompt,
            max_attempts=3,
            base_delay=2.0,
        )
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")

    last_exc: BaseException | None = None

    for attempt in range(max_attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            is_last_attempt = attempt == max_attempts - 1

            if is_last_attempt:
                logger.warning(
                    "with_retry exhausted %d attempts on %s: %s",
                    max_attempts,
                    fn.__name__,
                    exc,
                )
                raise

            if retryable_only and not is_retryable(exc):
                logger.debug(
                    "with_retry non-retryable exception on %s (aborting): %s",
                    fn.__name__,
                    exc,
                )
                raise

            delay = backoff_delay(attempt, base_delay=base_delay, max_delay=max_delay)
            retry_type = "rate-limit" if is_rate_limit(exc) else "transient"
            logger.warning(
                "with_retry %s error on %s (attempt %d/%d, retrying in %.1fs): %s",
                retry_type,
                fn.__name__,
                attempt + 1,
                max_attempts,
                delay,
                exc,
            )

            if on_retry is not None:
                try:
                    on_retry(attempt + 1, exc)
                except Exception:  # noqa: BLE001
                    pass  # Don't let callback errors interrupt retry logic

            await asyncio.sleep(delay)

    # Should not reach here, but satisfies type checker
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"with_retry: unexpected state after {max_attempts} attempts")
