"""Tests for src/services/retry_utils.py."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.services.retry_utils import (
    backoff_delay,
    is_rate_limit,
    is_retryable,
    with_retry,
)


class TestIsRetryable:
    def test_rate_limit_strings(self):
        assert is_retryable(Exception("Rate limit exceeded"))
        assert is_retryable(Exception("429 Too Many Requests"))
        assert is_retryable(Exception("rate_limit: TPM exceeded"))
        assert is_retryable(Exception("QUOTA limit"))
        assert is_retryable(Exception("Too many requests"))

    def test_server_error_strings(self):
        assert is_retryable(Exception("500 Internal Server Error"))
        assert is_retryable(Exception("503 Service Unavailable"))
        assert is_retryable(Exception("502 Bad Gateway"))
        assert is_retryable(Exception("timeout"))
        assert is_retryable(Exception("Request timed out"))

    def test_non_retryable_strings(self):
        assert not is_retryable(Exception("404 Not Found"))
        assert not is_retryable(Exception("Invalid API key"))
        assert not is_retryable(Exception("Permission denied"))


class TestIsRateLimit:
    def test_rate_limit(self):
        assert is_rate_limit(Exception("Rate limit exceeded"))
        assert is_rate_limit(Exception("429"))
        assert is_rate_limit(Exception("QUOTA"))
        assert is_rate_limit(Exception("Too many requests"))

    def test_not_rate_limit(self):
        assert not is_rate_limit(Exception("500 Server Error"))
        assert not is_rate_limit(Exception("Timeout error"))


class TestBackoffDelay:
    def test_exponential_growth(self):
        d0 = backoff_delay(0, base_delay=1.0, max_delay=60.0)
        d1 = backoff_delay(1, base_delay=1.0, max_delay=60.0)
        d2 = backoff_delay(2, base_delay=1.0, max_delay=60.0)
        assert 0.8 <= d0 <= 1.2  # jitter ±20%
        assert 1.6 <= d1 <= 2.4
        assert 3.2 <= d2 <= 4.8

    def test_capped_at_max_delay(self):
        d6 = backoff_delay(6, base_delay=1.0, max_delay=5.0)
        # With ±20% jitter, max value is 5.0 * 1.2 = 6.0
        assert d6 <= 6.0


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_attempt(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_retry(flaky, max_attempts=3)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("rate limit 429")
            return "ok"

        result = await with_retry(flaky, max_attempts=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_does_not_retry(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            raise ValueError("404 Not Found")

        with pytest.raises(ValueError, match="404"):
            await with_retry(flaky, max_attempts=3, retryable_only=True)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            raise ValueError("rate limit 429")

        with pytest.raises(ValueError, match="rate limit"):
            await with_retry(flaky, max_attempts=3, base_delay=0.01)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        call_count = 0
        callbacks = []

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("429 rate limit exceeded")
            return "ok"

        def on_retry(attempt, exc):
            callbacks.append((attempt, str(exc)))

        result = await with_retry(flaky, max_attempts=3, base_delay=0.01, on_retry=on_retry)
        assert result == "ok"
        assert len(callbacks) == 2
        assert callbacks[0][0] == 1
        assert callbacks[1][0] == 2

    @pytest.mark.asyncio
    async def test_max_attempts_must_be_positive(self):
        with pytest.raises(ValueError, match=">= 1"):
            await with_retry(AsyncMock(return_value="ok"), max_attempts=0)
