"""In-memory LRU cache for retrieval results.

Caches the top-K candidate list per (query_hash, tenant_id, department, top_k) so
repeated queries — especially hot-path questions like "KPI là gì?" —
return instantly without a Qdrant round-trip.

Cache key: sha1(query_lower + tenant_id + department + top_k)
TTL: 300 s (5 minutes)
Bypass: when as_of_date is set (policy version may differ)

IMPORTANT: department is included in the cache key to prevent cross-school data
leaks. Without it, a HUST user and a HUCE user with the same tenant_id would
share cached retrieval results, potentially leaking DEPARTMENT-scoped documents
from one school to another (see BUGS_FOUND.md cross-school leak analysis).

Usage
-----
    from src.retrieval.retrieval_cache import retrieval_cache

    key = cache.make_key(query, tenant_id, department="HUST", top_k=20)
    hit = cache.get(key)
    if hit is None:
        hit = await do_retrieval()
        cache.set(key, hit, ttl=300.0)
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from src.domain.schemas import RetrievalResult


@dataclass
class _CacheEntry:
    result: RetrievalResult
    expires_at: float  # monotonic seconds


class RetrievalCache:
    """Thread-safe LRU cache with TTL for retrieval results."""

    def __init__(self, max_size: int = 256, default_ttl: float = 300.0):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: dict[str, _CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        query: str,
        tenant_id: str,
        department: str,
        top_k: int,
    ) -> str:
        """Deterministic cache key — case-insensitive, whitespace-normalised.

        Includes department to prevent cross-school data leaks: two users
        from different departments but the same tenant must not share a
        cached result because their access filters differ.
        """
        normalized = " ".join(query.lower().split())
        # Normalise department to uppercase to match UserContext convention
        dept_normalized = department.strip().upper()
        raw = f"{normalized}|{tenant_id}|{dept_normalized}|{top_k}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def get(self, key: str) -> RetrievalResult | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._hits += 1
            return entry.result

    def set(self, key: str, result: RetrievalResult, ttl: float | None = None) -> None:
        with self._lock:
            # Evict oldest entry when at capacity
            if len(self._store) >= self._max_size and key not in self._store:
                oldest_key = min(
                    self._store,
                    key=lambda k: self._store[k].expires_at,
                )
                del self._store[oldest_key]
            self._store[key] = _CacheEntry(
                result=result,
                expires_at=time.monotonic() + (ttl if ttl is not None else self._default_ttl),
            )

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }


# Module-level singleton — created lazily so tests can patch it.
_retrieval_cache: RetrievalCache | None = None
_cache_lock = threading.Lock()


def get_retrieval_cache() -> RetrievalCache:
    global _retrieval_cache
    if _retrieval_cache is None:
        with _cache_lock:
            if _retrieval_cache is None:
                _retrieval_cache = RetrievalCache()
    return _retrieval_cache


# Convenience alias used by workflow
retrieval_cache = get_retrieval_cache
