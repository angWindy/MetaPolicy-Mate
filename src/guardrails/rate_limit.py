from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """Bounded per-identity sliding-window limiter for one application process."""

    def __init__(self, *, max_requests: int, window_seconds: float, max_buckets: int = 10_000) -> None:
        if max_requests < 1 or window_seconds <= 0 or max_buckets < 1:
            raise ValueError("Rate-limit settings must be positive.")
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self.max_buckets = max_buckets
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, identity_key: str, *, now: float | None = None) -> RateLimitDecision:
        current = time.monotonic() if now is None else float(now)
        cutoff = current - self.window_seconds
        with self._lock:
            bucket = self._buckets.setdefault(identity_key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(int(self.window_seconds - (current - bucket[0])) + 1, 1)
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
            bucket.append(current)
            self._prune_empty_or_old(cutoff)
            return RateLimitDecision(allowed=True)

    def _prune_empty_or_old(self, cutoff: float) -> None:
        for key in list(self._buckets):
            bucket = self._buckets[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                self._buckets.pop(key, None)
        if len(self._buckets) <= self.max_buckets:
            return
        oldest = sorted(self._buckets, key=lambda key: self._buckets[key][-1])
        for key in oldest[: len(self._buckets) - self.max_buckets]:
            self._buckets.pop(key, None)


__all__ = ["InMemoryRateLimiter", "RateLimitDecision"]
