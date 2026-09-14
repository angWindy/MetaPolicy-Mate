from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Protocol

from src.domain.schemas import SparseVectorData
from src.rag.config import RAGSettings
from src.retrieval.query_transform import (
    ARTICLE_PATTERN,
    CLAUSE_PATTERN,
    DOCUMENT_NUMBER_PATTERN,
    FORM_CODE_PATTERN,
    normalize_unicode,
    normalize_whitespace,
    validate_query,
)

FORM_LABEL_PATTERN = re.compile(
    r"\b(?:mẫu|mau)\s+\d+[a-z]?\b",
    flags=re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
SPARSE_INDEX_MODULUS = 2**31 - 1


class SparseEmbeddingProvider(Protocol):
    model_name: str
    model_version: str

    def sparse_embed_query(self, query: str) -> SparseVectorData: ...

    def sparse_embed_documents(self, documents: list[str]) -> list[SparseVectorData]: ...


def _protected_spans(text: str) -> list[tuple[int, int]]:
    spans = [
        match.span()
        for pattern in (
            DOCUMENT_NUMBER_PATTERN,
            FORM_CODE_PATTERN,
            FORM_LABEL_PATTERN,
            ARTICLE_PATTERN,
            CLAUSE_PATTERN,
        )
        for match in pattern.finditer(text)
    ]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def tokenize_sparse(text: str) -> list[str]:
    normalized = normalize_whitespace(normalize_unicode(text))
    spans = _protected_spans(normalized)
    identifiers = [normalized[start:end] for start, end in spans]

    remainder = list(normalized)
    for start, end in spans:
        remainder[start:end] = " " * (end - start)
    words = [match.group(0).lower() for match in WORD_PATTERN.finditer("".join(remainder))]
    ngrams = [
        " ".join(words[index : index + size])
        for size in (2, 3)
        for index in range(len(words) - size + 1)
    ]
    return [*identifiers, *words, *ngrams]


def _canonical_token(token: str) -> str:
    return normalize_unicode(token).casefold()


def _token_index(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SPARSE_INDEX_MODULUS


def _token_weight(token: str, frequency: int) -> float:
    if any(
        pattern.fullmatch(token)
        for pattern in (
            DOCUMENT_NUMBER_PATTERN,
            FORM_CODE_PATTERN,
            FORM_LABEL_PATTERN,
            ARTICLE_PATTERN,
            CLAUSE_PATTERN,
        )
    ):
        base_weight = 3.0
    elif " " in token:
        base_weight = 1.75
    else:
        base_weight = 1.0
    return base_weight * (1.0 + math.log(frequency))


class HashedSparseEmbeddingProvider:
    """Deterministic lexical sparse vectors compatible with Qdrant."""

    def __init__(self, model_name: str = "hashed-lexical", model_version: str = "1"):
        self.model_name = model_name
        self.model_version = model_version

    def _embed(self, text: str) -> SparseVectorData:
        tokens = [_canonical_token(token) for token in tokenize_sparse(text)]
        frequencies = Counter(tokens)
        by_index: dict[int, float] = {}
        for token, frequency in frequencies.items():
            index = _token_index(token)
            by_index[index] = by_index.get(index, 0.0) + _token_weight(
                token,
                frequency,
            )
        if not by_index:
            raise ValueError("Text must contain at least one searchable token.")
        indices = sorted(by_index)
        return SparseVectorData(
            indices=indices,
            values=[by_index[index] for index in indices],
        )

    def sparse_embed_query(self, query: str) -> SparseVectorData:
        validate_query(query)
        return self._embed(query)

    def sparse_embed_documents(self, documents: list[str]) -> list[SparseVectorData]:
        return [self._embed(document) for document in documents]


def build_sparse_embedding_provider(settings: RAGSettings) -> SparseEmbeddingProvider:
    return HashedSparseEmbeddingProvider(
        model_name=settings.sparse_embedding_model,
        model_version=settings.sparse_embedding_version,
    )
