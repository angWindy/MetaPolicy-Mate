"""Tests for src/services/embeddings.py ResilientEmbeddingProvider.

Core contracts tested:
1. Retry on transient errors (rate-limit).
2. Fallback when primary exhausted.
3. Non-retryable errors propagate immediately.
4. All-providers-fail raises RuntimeError.
"""

from __future__ import annotations

import pytest

from src.services.embeddings import ResilientEmbeddingProvider


class _FakeProvider:
    """Minimal CachedDenseEmbeddingProvider stub with controlled failure/success."""

    def __init__(self, name: str = "fake", dims: int = 4):
        self.model_name = name
        self.model_version = "v1"
        self._dims = dims
        self.call_count = 0
        # Results returned in order; exceptions cause failures.
        self._results: list[object] = []

    @property
    def dimensions(self) -> int:
        return self._dims

    def set_results(self, results: list[object]) -> None:
        self._results = list(results)

    async def embed_query(self, text: str):
        self.call_count += 1
        if self._results:
            result = self._results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return [0.1] * self._dims

    async def embed_documents(self, texts: list[str], **kw):
        self.call_count += 1
        if self._results:
            result = self._results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return [[0.1] * self._dims for _ in texts]


class _MockSettings:
    embedding_max_retries = 2
    embedding_retry_base_delay = 0.001
    embedding_retry_max_delay = 0.1
    embedding_dimensions = 4

    @property
    def embedding_fallback_provider_list(self):
        return []


@pytest.mark.asyncio
async def test_embed_query_succeeds_without_retry():
    primary = _FakeProvider(name="primary", dims=4)
    primary.set_results([[0.5, 0.5, 0.5, 0.5]])

    provider = ResilientEmbeddingProvider(primary=primary, settings=_MockSettings())
    result = await provider.embed_query("hello")

    assert result == [0.5, 0.5, 0.5, 0.5]
    assert primary.call_count == 1


@pytest.mark.asyncio
async def test_embed_query_retries_on_rate_limit_and_succeeds():
    """Rate-limit on first call → retry → second call succeeds."""
    primary = _FakeProvider(name="primary", dims=4)
    primary.set_results([
        RuntimeError("429 rate limit exceeded"),
        [0.5, 0.5, 0.5, 0.5],
    ])

    provider = ResilientEmbeddingProvider(primary=primary, settings=_MockSettings())
    result = await provider.embed_query("hello")

    assert result == [0.5, 0.5, 0.5, 0.5]
    assert primary.call_count == 2


@pytest.mark.asyncio
async def test_embed_query_exhausts_retries_then_falls_back():
    """Both retries fail → fallback is tried and succeeds."""
    primary = _FakeProvider(name="primary", dims=4)
    primary.set_results([
        RuntimeError("429 rate limit"),
        RuntimeError("429 rate limit"),
        [0.5, 0.5, 0.5, 0.5],
    ])
    fallback = _FakeProvider(name="hash", dims=4)
    fallback.set_results([[0.9, 0.9, 0.9, 0.9]])

    provider = ResilientEmbeddingProvider(primary=primary, settings=_MockSettings())
    provider._fallback_providers = [fallback]

    result = await provider.embed_query("hello")

    assert result == [0.9, 0.9, 0.9, 0.9]
    assert primary.call_count == 2
    assert fallback.call_count == 1


@pytest.mark.asyncio
async def test_embed_query_raises_when_primary_fails_and_no_fallback():
    """No fallback configured and primary fails all retries → RuntimeError."""
    primary = _FakeProvider(name="primary", dims=4)
    primary.set_results([
        RuntimeError("429 rate limit"),
        RuntimeError("429 rate limit"),
    ])
    provider = ResilientEmbeddingProvider(primary=primary, settings=_MockSettings())

    with pytest.raises(RuntimeError, match="failed for all embedding providers"):
        await provider.embed_query("hello")

    assert primary.call_count == 2


@pytest.mark.asyncio
async def test_non_retryable_error_propagates():
    """Non-retryable errors (e.g., 404) are caught and wrapped as 'all providers failed'.

    The non-retryable error is logged and the outer loop tries next fallback.
    Since there is no fallback, this becomes "all providers failed".
    """
    primary = _FakeProvider(name="primary", dims=4)
    primary.set_results([
        RuntimeError("404 Not Found: invalid API key"),
    ])

    provider = ResilientEmbeddingProvider(primary=primary, settings=_MockSettings())

    with pytest.raises(RuntimeError, match="failed for all embedding providers"):
        await provider.embed_query("hello")

    assert primary.call_count == 1
