from __future__ import annotations

import math
import re
from collections import Counter

from src.retrieval.normalization import is_vn_normalize_enabled


_LEGACY_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Tokenise text using the active lexical tokenizer.

    When ``VN_NORMALIZE_ENABLED`` is true the Vietnamese tokenizer
    ``vn_tokenize`` is used (diacritic-insensitive). Otherwise the
    legacy regex tokenizer is used so existing BM25 scores remain
    reproducible during the transition.
    """
    if not isinstance(text, str):
        return []
    if is_vn_normalize_enabled():
        # Lazy import so the normalization module is only loaded when
        # the flag is on (avoids the lru_cache cost in legacy mode).
        from src.retrieval.normalization import vn_tokenize

        return vn_tokenize(text)
    return _LEGACY_TOKEN_RE.findall(text.lower())


def bm25_search(query: str, documents: list[dict], limit: int) -> list[tuple[str, float]]:
    if not documents:
        return []
    tokenized_documents = [tokenize(item["embedding_text"]) for item in documents]
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    document_count = len(tokenized_documents)
    average_length = sum(len(tokens) for tokens in tokenized_documents) / document_count
    document_frequency = Counter()
    for tokens in tokenized_documents:
        document_frequency.update(set(tokens))

    k1 = 1.5
    b = 0.75
    results: list[tuple[str, float]] = []
    for item, tokens in zip(documents, tokenized_documents, strict=True):
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            df = document_frequency[token]
            if not df:
                continue
            inverse_frequency = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
            frequency = frequencies[token]
            denominator = frequency + k1 * (1 - b + b * len(tokens) / max(average_length, 1))
            score += inverse_frequency * (frequency * (k1 + 1)) / max(denominator, 1e-9)
        if score > 0:
            results.append((item["chunk_id"], score))
    return sorted(results, key=lambda item: item[1], reverse=True)[:limit]
