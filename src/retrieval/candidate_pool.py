from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from src.domain.schemas import Candidate

DEFINITION_SECTION_MARKERS = (
    "định nghĩa",
    "giải thích từ ngữ",
    "thuật ngữ",
    "definitions",
    "glossary",
)
DEFINITION_TYPES = {"definition", "definitions", "glossary", "term"}


@dataclass(frozen=True)
class CandidateDiversity:
    candidate_count: int
    unique_chunk_ratio: float
    unique_content_ratio: float
    document_diversity_ratio: float
    max_chunks_per_document: int


def _is_definition(candidate: Candidate) -> bool:
    metadata = candidate.metadata
    if metadata.get("is_definition") is True:
        return True
    chunk_type = str(metadata.get("chunk_type") or metadata.get("type") or "")
    if chunk_type.casefold() in DEFINITION_TYPES:
        return True
    section = str(metadata.get("section") or "").casefold()
    if any(marker in section for marker in DEFINITION_SECTION_MARKERS):
        return True
    content = candidate.content.casefold().lstrip()
    return content.startswith("trong văn bản này, các từ ngữ dưới đây")


def preserve_definition_chunks(candidates: list[Candidate]) -> list[Candidate]:
    """Return definition candidates that conservative cleaning must protect."""

    return [candidate for candidate in candidates if _is_definition(candidate)]


def _content_hash(candidate: Candidate) -> str | None:
    value = candidate.metadata.get("content_hash")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _append_duplicate_id(candidate: Candidate, duplicate_chunk_id: str) -> Candidate:
    metadata = dict(candidate.metadata)
    duplicate_ids = list(metadata.get("exact_duplicate_chunk_ids", []))
    if duplicate_chunk_id != candidate.chunk_id and duplicate_chunk_id not in duplicate_ids:
        duplicate_ids.append(duplicate_chunk_id)
    if duplicate_ids:
        metadata["exact_duplicate_chunk_ids"] = duplicate_ids
    return candidate.model_copy(update={"metadata": metadata})


def remove_exact_duplicates(candidates: list[Candidate]) -> list[Candidate]:
    """Dedupe by chunk_id first, then by non-empty content_hash."""

    by_chunk_id: dict[str, Candidate] = {}
    chunk_order: list[str] = []
    for candidate in candidates:
        if candidate.chunk_id not in by_chunk_id:
            by_chunk_id[candidate.chunk_id] = candidate
            chunk_order.append(candidate.chunk_id)

    unique_by_chunk = [by_chunk_id[chunk_id] for chunk_id in chunk_order]
    by_hash: dict[str, Candidate] = {}
    hash_position: dict[str, int] = {}
    selected: list[Candidate] = []
    for candidate in unique_by_chunk:
        content_hash = _content_hash(candidate)
        if content_hash is None:
            selected.append(candidate)
            continue
        existing = by_hash.get(content_hash)
        if existing is None:
            hash_position[content_hash] = len(selected)
            by_hash[content_hash] = candidate
            selected.append(candidate)
            continue

        position = hash_position[content_hash]
        if _is_definition(candidate) and not _is_definition(existing):
            replacement = _append_duplicate_id(candidate, existing.chunk_id)
            selected[position] = replacement
            by_hash[content_hash] = replacement
        else:
            kept = _append_duplicate_id(existing, candidate.chunk_id)
            selected[position] = kept
            by_hash[content_hash] = kept
    return selected


def _legal_locator(candidate: Candidate) -> tuple[str, str, str]:
    metadata = candidate.metadata
    return (
        str(metadata.get("article") or "").strip().casefold(),
        str(metadata.get("clause") or "").strip().casefold(),
        str(metadata.get("section") or "").strip().casefold(),
    )


def _different_legal_provisions(first: Candidate, second: Candidate) -> bool:
    first_locator = _legal_locator(first)
    second_locator = _legal_locator(second)
    return bool(
        any(first_locator)
        and any(second_locator)
        and first_locator != second_locator
    )


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _tfidf_matrix(contents: list[str]) -> np.ndarray:
    tokenized: list[list[str]] = []
    for content in contents:
        words = re.findall(r"\w+", content.casefold(), flags=re.UNICODE)
        bigrams = [f"{left} {right}" for left, right in zip(words, words[1:])]
        tokenized.append([*words, *bigrams])
    vocabulary = sorted({token for tokens in tokenized for token in tokens})
    if not vocabulary:
        return np.zeros((len(contents), 0), dtype=float)
    token_index = {token: index for index, token in enumerate(vocabulary)}
    document_frequency = Counter(
        token for tokens in tokenized for token in set(tokens)
    )
    matrix = np.zeros((len(contents), len(vocabulary)), dtype=float)
    document_count = len(contents)
    for row, tokens in enumerate(tokenized):
        frequencies = Counter(tokens)
        for token, frequency in frequencies.items():
            inverse_document_frequency = (
                math.log(
                    (1 + document_count) / (1 + document_frequency[token])
                )
                + 1.0
            )
            matrix[row, token_index[token]] = (
                1.0 + math.log(frequency)
            ) * inverse_document_frequency
    return matrix


def remove_near_duplicates(
    candidates: list[Candidate],
    *,
    similarity_threshold: float = 0.95,
) -> list[Candidate]:
    """Remove highly similar overlap chunks without performing relevance selection."""

    if not 0.0 <= similarity_threshold <= 1.0:
        raise ValueError("similarity_threshold must be between 0 and 1.")
    exact_unique = remove_exact_duplicates(candidates)
    if len(exact_unique) < 2:
        return exact_unique

    matrix = _tfidf_matrix([candidate.content for candidate in exact_unique])
    if matrix.shape[1] == 0:
        return exact_unique

    protected = {
        candidate.chunk_id for candidate in preserve_definition_chunks(exact_unique)
    }
    selected_indices: list[int] = []
    for current_index, candidate in enumerate(exact_unique):
        if candidate.chunk_id in protected:
            retained_indices: list[int] = []
            for selected_index in selected_indices:
                existing = exact_unique[selected_index]
                if existing.chunk_id in protected:
                    retained_indices.append(selected_index)
                    continue
                if existing.document_id != candidate.document_id:
                    retained_indices.append(selected_index)
                    continue
                if _different_legal_provisions(existing, candidate):
                    retained_indices.append(selected_index)
                    continue
                similarity = _cosine_similarity(
                    matrix[selected_index], matrix[current_index]
                )
                if similarity < similarity_threshold:
                    retained_indices.append(selected_index)
            selected_indices = retained_indices
            selected_indices.append(current_index)
            continue
        is_duplicate = False
        for selected_index in selected_indices:
            existing = exact_unique[selected_index]
            if existing.document_id != candidate.document_id:
                continue
            if _different_legal_provisions(existing, candidate):
                continue
            similarity = _cosine_similarity(matrix[selected_index], matrix[current_index])
            if similarity >= similarity_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            selected_indices.append(current_index)
    return [exact_unique[index] for index in selected_indices]


def cap_chunks_per_document(
    candidates: list[Candidate],
    *,
    limit: int,
    max_chunks_per_document: int = 4,
) -> list[Candidate]:
    if limit < 1:
        raise ValueError("limit must be positive.")
    if not 1 <= max_chunks_per_document <= 4:
        raise ValueError("max_chunks_per_document must be between 1 and 4.")

    unique = remove_exact_duplicates(candidates)
    by_document: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in unique:
        by_document[candidate.document_id].append(candidate)

    selected_ids: set[str] = set()
    for document_candidates in by_document.values():
        definitions = preserve_definition_chunks(document_candidates)
        definition_ids = {candidate.chunk_id for candidate in definitions}
        chosen = definitions[:max_chunks_per_document]
        remaining = max_chunks_per_document - len(chosen)
        if remaining:
            chosen.extend(
                candidate
                for candidate in document_candidates
                if candidate.chunk_id not in definition_ids
            )
            chosen = chosen[:max_chunks_per_document]
        selected_ids.update(candidate.chunk_id for candidate in chosen)

    selected = [
        candidate for candidate in unique if candidate.chunk_id in selected_ids
    ]
    return selected[:limit]


def calculate_candidate_diversity(
    candidates: list[Candidate],
) -> CandidateDiversity:
    count = len(candidates)
    if count == 0:
        return CandidateDiversity(0, 0.0, 0.0, 0.0, 0)
    chunk_ids = {candidate.chunk_id for candidate in candidates}
    hashes = {
        content_hash
        for candidate in candidates
        if (content_hash := _content_hash(candidate)) is not None
    }
    content_units = len(hashes) + sum(
        _content_hash(candidate) is None for candidate in candidates
    )
    document_counts = Counter(candidate.document_id for candidate in candidates)
    return CandidateDiversity(
        candidate_count=count,
        unique_chunk_ratio=len(chunk_ids) / count,
        unique_content_ratio=content_units / count,
        document_diversity_ratio=len(document_counts) / count,
        max_chunks_per_document=max(document_counts.values()),
    )


def clean_candidate_pool(
    candidates: list[Candidate],
    *,
    limit: int,
    max_chunks_per_document: int = 4,
    near_duplicate_threshold: float = 0.95,
) -> list[Candidate]:
    exact_unique = remove_exact_duplicates(candidates)
    near_unique = remove_near_duplicates(
        exact_unique,
        similarity_threshold=near_duplicate_threshold,
    )
    return cap_chunks_per_document(
        near_unique,
        limit=limit,
        max_chunks_per_document=max_chunks_per_document,
    )
