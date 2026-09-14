from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Protocol

import numpy as np

from src.domain.schemas import (
    Candidate,
    Latency,
    RerankRequest,
    RerankResult,
    RetrievalStatus,
)
from src.rag.config import RAGSettings
from src.retrieval.candidate_pool import remove_exact_duplicates

logger = logging.getLogger(__name__)


class RerankServiceProtocol(Protocol):
    async def rerank(self, request: RerankRequest) -> RerankResult: ...


def _rerank_score(candidate: Candidate) -> float:
    if candidate.rerank_score is None:
        raise ValueError("All thresholded candidates must have a rerank_score.")
    if not math.isfinite(candidate.rerank_score):
        raise ValueError("rerank_score must be finite.")
    return float(candidate.rerank_score)


def apply_score_threshold(
    candidates: Sequence[Candidate],
    *,
    threshold: float | None,
) -> list[Candidate]:
    """Apply an evaluation-calibrated raw-score threshold without rescaling."""

    if threshold is None:
        return list(candidates)
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite.")
    return [candidate for candidate in candidates if _rerank_score(candidate) >= threshold]


def detect_score_gap(
    candidates: Sequence[Candidate],
    *,
    minimum_gap: float | None,
    minimum_contexts: int = 3,
    maximum_contexts: int = 5,
) -> int | None:
    """Return a context cutoff when a calibrated raw-score gap is detected."""

    if minimum_gap is None:
        return None
    if not math.isfinite(minimum_gap) or minimum_gap <= 0.0:
        raise ValueError("minimum_gap must be a positive finite number.")
    if minimum_contexts < 1 or maximum_contexts < minimum_contexts:
        raise ValueError("Invalid score-gap context bounds.")

    upper = min(len(candidates), maximum_contexts)
    for cutoff in range(minimum_contexts, upper):
        gap = _rerank_score(candidates[cutoff - 1]) - _rerank_score(candidates[cutoff])
        if gap >= minimum_gap:
            return cutoff
    return None


def _term_frequency_matrix(candidates: Sequence[Candidate]) -> np.ndarray:
    tokenized = [
        re.findall(r"\w+", candidate.content.casefold(), flags=re.UNICODE)
        for candidate in candidates
    ]
    vocabulary = sorted({token for tokens in tokenized for token in tokens})
    if not vocabulary:
        return np.zeros((len(candidates), 0), dtype=float)
    token_index = {token: index for index, token in enumerate(vocabulary)}
    matrix = np.zeros((len(candidates), len(vocabulary)), dtype=float)
    for row, tokens in enumerate(tokenized):
        for token, count in Counter(tokens).items():
            matrix[row, token_index[token]] = 1.0 + math.log(count)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms != 0.0)


def apply_mmr(
    candidates: Sequence[Candidate],
    *,
    limit: int,
    lambda_mult: float = 0.85,
) -> list[Candidate]:
    """Select diverse evidence using rank relevance and lexical cosine similarity."""

    if limit < 1:
        raise ValueError("limit must be positive.")
    if not 0.0 <= lambda_mult <= 1.0:
        raise ValueError("lambda_mult must be between 0 and 1.")
    pool: list[Candidate] = []
    seen_content: set[str] = set()
    for candidate in remove_exact_duplicates(list(candidates)):
        normalized_content = " ".join(candidate.content.casefold().split())
        if normalized_content and normalized_content in seen_content:
            continue
        if normalized_content:
            seen_content.add(normalized_content)
        pool.append(candidate)
    if len(pool) <= 1:
        return pool[:limit]

    vectors = _term_frequency_matrix(pool)
    # Rank relevance avoids assuming a CrossEncoder score range or calibration.
    denominator = max(len(pool) - 1, 1)
    relevance = np.asarray(
        [1.0 - (rank / denominator) for rank in range(len(pool))],
        dtype=float,
    )
    selected_indices: list[int] = []
    remaining = set(range(len(pool)))
    while remaining and len(selected_indices) < limit:
        best_index = min(
            remaining,
            key=lambda index: (
                -(
                    lambda_mult * relevance[index]
                    - (1.0 - lambda_mult)
                    * max(
                        (float(np.dot(vectors[index], vectors[chosen])) for chosen in selected_indices),
                        default=0.0,
                    )
                ),
                index,
            ),
        )
        selected_indices.append(best_index)
        remaining.remove(best_index)
    return [pool[index] for index in selected_indices]


def cap_final_chunks_per_document(
    candidates: Sequence[Candidate],
    *,
    limit: int,
    max_chunks_per_document: int = 2,
) -> list[Candidate]:
    if limit < 1:
        raise ValueError("limit must be positive.")
    if not 1 <= max_chunks_per_document <= 2:
        raise ValueError("max_chunks_per_document must be between 1 and 2.")
    counts: defaultdict[str, int] = defaultdict(int)
    selected: list[Candidate] = []
    for candidate in remove_exact_duplicates(list(candidates)):
        if counts[candidate.document_id] >= max_chunks_per_document:
            continue
        selected.append(candidate)
        counts[candidate.document_id] += 1
        if len(selected) == limit:
            break
    return selected


def select_final_contexts(
    candidates: Sequence[Candidate],
    *,
    final_limit: int,
    pre_diversity_limit: int = 20,
    max_chunks_per_document: int = 2,
    mmr_lambda: float = 0.85,
    score_gap_min: float | None = None,
) -> list[Candidate]:
    if not 3 <= final_limit <= 5:
        raise ValueError("final_limit must be between 3 and 5.")
    if pre_diversity_limit < final_limit:
        raise ValueError("pre_diversity_limit must not be smaller than final_limit.")

    pool = list(candidates)[:pre_diversity_limit]
    gap_cutoff = detect_score_gap(
        pool,
        minimum_gap=score_gap_min,
        minimum_contexts=3,
        maximum_contexts=final_limit,
    )
    target = gap_cutoff or final_limit
    diversified = apply_mmr(pool, limit=len(pool) or 1, lambda_mult=mmr_lambda)
    return cap_final_chunks_per_document(
        diversified,
        limit=target,
        max_chunks_per_document=max_chunks_per_document,
    )


async def rerank_evidence(
    *,
    original_query: str,
    candidates: Sequence[Candidate],
    reranker_service: RerankServiceProtocol,
    settings: RAGSettings,
) -> RerankResult:
    """Rerank up to 60 candidates, threshold, diversify, and select 3--5 contexts."""

    started = time.perf_counter()
    rerank_input = list(candidates)[: settings.rerank_candidate_limit]
    reranked = await reranker_service.rerank(
        RerankRequest(
            original_query=original_query,
            candidates=rerank_input,
            limit=settings.rerank_pre_diversity_limit,
        )
    )
    warnings = list(reranked.warnings)

    if reranked.status in {
        RetrievalStatus.NOT_FOUND,
        RetrievalStatus.FORBIDDEN,
        RetrievalStatus.CONFLICT,
    }:
        selected: list[Candidate] = []
        status = reranked.status
    elif all(candidate.rerank_score is None for candidate in reranked.candidates):
        selected = select_final_contexts(
            reranked.candidates,
            final_limit=settings.final_context_limit,
            pre_diversity_limit=settings.rerank_pre_diversity_limit,
            max_chunks_per_document=settings.final_max_chunks_per_document,
            mmr_lambda=settings.rerank_mmr_lambda,
        )
        status = RetrievalStatus.PARTIAL
    else:
        thresholded = apply_score_threshold(
            reranked.candidates,
            threshold=settings.rerank_score_threshold,
        )
        if not thresholded:
            selected = []
            status = RetrievalStatus.WEAK
            warnings.append("No candidate met the configured rerank score threshold.")
        else:
            selected = select_final_contexts(
                thresholded,
                final_limit=settings.final_context_limit,
                pre_diversity_limit=settings.rerank_pre_diversity_limit,
                max_chunks_per_document=settings.final_max_chunks_per_document,
                mmr_lambda=settings.rerank_mmr_lambda,
                score_gap_min=settings.rerank_score_gap_min,
            )
            status = (
                RetrievalStatus.SUFFICIENT
                if len(selected) >= 1
                else RetrievalStatus.PARTIAL
            )

    elapsed_ms = (time.perf_counter() - started) * 1000
    # Structured latency log for reranking leg.
    top_score = selected[0].rerank_score if selected else None
    logger.info(
        "rerank_evidence_latency query_len=%d input_candidates=%d output_candidates=%d "
        "rerank_ms=%.1f total_ms=%.1f top_score=%s status=%s",
        len(original_query),
        len(rerank_input),
        len(selected),
        reranked.latency.rerank_ms,
        elapsed_ms,
        f"{top_score:.3f}" if top_score is not None else "None",
        status.value,
    )
    return RerankResult(
        status=status,
        original_query=original_query,
        candidates=selected,
        warnings=warnings,
        latency=Latency(
            rerank_ms=reranked.latency.rerank_ms,
            evidence_gate_ms=max(elapsed_ms - reranked.latency.total_ms, 0.0),
            total_ms=elapsed_ms,
        ),
    )
