"""In-memory LRU cache for reranked results.

Caches the reranked candidate list per (query_hash, candidate_ids_hash) so
repeated queries with the same candidates return instantly without re-running
the expensive CrossEncoder reranker.

Cache key: sha1(query_hash + sorted(candidate_ids))
TTL: 300 s (5 minutes)

This is separate from retrieval_cache because:
1. Retrieval cache key includes top_k, but rerank cache key must include
   the full list of candidate IDs
2. Retrieval cache is invalidated by as_of_date, but rerank cache is not
3. They have different TTL requirements in theory (could be different later)

Usage
-----
    from src.retrieval.rerank_cache import rerank_cache

    # Check cache before reranking
    candidate_ids = [c.chunk_id for c in candidates]
    key = rerank_cache.make_key(query, candidate_ids)
    cached = rerank_cache.get(key)
    if cached is not None:
        return cached
    
    # After reranking, store result
    rerank_cache.set(key, scored_candidates, ttl=300.0)
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

from src.domain.schemas import Candidate, RetrievalResult


@dataclass
class _RerankCacheEntry:
    candidates: list[Candidate]
    expires_at: float  # monotonic seconds


class RerankCache:
    """Thread-safe LRU cache with TTL for reranked results."""

    def __init__(self, max_size: int = 256, default_ttl: float = 300.0):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._store: dict[str, _RerankCacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(
        query: str,
        candidate_ids: Sequence[str],
    ) -> str:
        """Deterministic cache key from query and candidate IDs.

        The candidate IDs are sorted so that the same candidates in any order
        produce the same cache key.
        """
        normalized_query = " ".join(query.lower().split())
        sorted_ids = "|".join(sorted(candidate_ids))
        raw = f"{normalized_query}|{sorted_ids}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def get(self, key: str) -> list[Candidate] | None:
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
            return entry.candidates

    def set(
        self,
        key: str,
        candidates: list[Candidate],
        ttl: float | None = None,
    ) -> None:
        with self._lock:
            # Evict oldest entry when at capacity
            if len(self._store) >= self._max_size and key not in self._store:
                oldest_key = min(
                    self._store,
                    key=lambda k: self._store[k].expires_at,
                )
                del self._store[oldest_key]
            self._store[key] = _RerankCacheEntry(
                candidates=candidates,
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


# Module-level singleton
_rerank_cache: RerankCache | None = None
_cache_lock = threading.Lock()


def get_rerank_cache() -> RerankCache:
    global _rerank_cache
    if _rerank_cache is None:
        with _cache_lock:
            if _rerank_cache is None:
                _rerank_cache = RerankCache()
    return _rerank_cache


# Convenience alias
rerank_cache = get_rerank_cache()
