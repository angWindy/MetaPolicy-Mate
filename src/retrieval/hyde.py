"""Hypothetical Document Embedding (HyDE) — LLM-based query rewrite.

Standard embedding models rank a query against chunk embeddings. When the
user's wording diverges from the chunk's surface form (e.g. "học phí Tiến
sĩ toàn khóa" vs. a chunk that just lists tiers), dense retrieval misses.

HyDE closes the gap by asking the generator to write a hypothetical
passage that *would* answer the query, then embedding *that* passage
instead of the raw query. The hypothesis is densest in the same chunk
vocabulary that the answer lives in.

This module is intentionally pluggable:
- The generator is consumed via a small async protocol so it stays
  testable without a real LLM key.
- The passage is cached by query hash so repeated queries don't pay
  LLM cost twice.
- A min query length gate skips HyDE for short identifier queries
  (e.g. "Quyết định 7737") where embedding the original query already
  hits the document number embedding.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Protocol

logger = logging.getLogger(__name__)


HYDE_PROMPT_TEMPLATE = """Bạn là trợ lý tra cứu văn bản nội bộ. Hãy viết một đoạn văn ngắn (3-5 câu) theo phong cách của một quyết định hoặc quy chế đại học bằng tiếng Việt, trả lời trực tiếp câu hỏi dưới đây. Không cần dẫn nguồn, không cần cảnh báo, chỉ viết nội dung như thể nó nằm trong văn bản.

Câu hỏi: {query}

Đoạn văn:"""


class HydeGenerator(Protocol):
    """Tiny protocol — any LLM that takes a prompt and returns text."""

    async def ainvoke(self, prompt: str) -> object: ...


class HydePassage(str):
    """Marker subclass so type-checkers can tell HyDE outputs from raw queries."""

    __slots__ = ()


def is_identifier_like(query: str) -> bool:
    """True if the query is dominated by a document/article identifier.

    For these queries, embedding the original query already hits the
    document number / article embedding, so HyDE adds no signal.
    """
    has_doc_number = bool(re.search(r"\d{1,6}/Q[ĐD]-[A-ZÀ-ỸĐ0-9]+", query))
    has_article_clause = bool(re.search(r"\b(điều|dieu|khoản|khoan)\s+\d+", query, re.IGNORECASE))
    has_heavy_numbers = bool(re.search(r"\b\d{4,}\b", query))
    return has_doc_number or has_article_clause or has_heavy_numbers


def should_apply_hyde(query: str, *, min_chars: int = 12) -> bool:
    """Top-level gate: don't bother if query is short or identifier-heavy."""
    if len(query.strip()) < min_chars:
        return False
    if is_identifier_like(query):
        return False
    return True


def hash_query(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]


class HydeCache:
    """Process-local LRU for hyde passages. Avoids double-LLM cost on retries."""

    def __init__(self, max_size: int = 256) -> None:
        self._store: dict[str, str] = {}
        self._order: list[str] = []
        self._max_size = max_size

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        if key in self._store:
            self._order.remove(key)
        self._store[key] = value
        self._order.append(key)
        if len(self._order) > self._max_size:
            oldest = self._order.pop(0)
            self._store.pop(oldest, None)

    def clear(self) -> None:
        self._store.clear()
        self._order.clear()


default_cache = HydeCache()


async def generate_hyde_passage(
    query: str,
    llm: HydeGenerator,
    *,
    cache: HydeCache | None = None,
    timeout: float = 15.0,
) -> str | None:
    """Run the HyDE prompt. Returns None on any failure (best-effort).

    The output is a hypothetical passage, not an answer. It is bounded
    by `timeout` so an LLM stall cannot block retrieval.
    """
    if not should_apply_hyde(query):
        return None
    cache = cache or default_cache
    key = hash_query(query)
    cached = cache.get(key)
    if cached is not None:
        return cached
    prompt = HYDE_PROMPT_TEMPLATE.format(query=query.strip())
    try:
        raw = await asyncio.wait_for(llm.ainvoke(prompt), timeout=timeout)
    except (TimeoutError, Exception) as exc:
        logger.warning("HyDE generation failed: %s: %s", type(exc).__name__, exc)
        return None
    text = _extract_text(raw)
    if not text:
        return None
    cleaned = _normalise_passage(text)
    if not cleaned:
        return None
    cache.set(key, cleaned)
    return cleaned


def _extract_text(raw: object) -> str:
    """Tolerate a few possible LLM response shapes without coupling to provider."""
    if raw is None:
        return ""
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        answer = raw.get("answer")
        if isinstance(answer, str):
            return answer
    return str(raw)


def _normalise_passage(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Strip a leading prefix like "Đoạn văn:" the model sometimes echoes.
    text = re.sub(r"^(đoạn văn|trả lời|đáp án)\s*[:\-]\s*", "", text, flags=re.IGNORECASE)
    return text.strip()
