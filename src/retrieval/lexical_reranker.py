"""Lexical fallback reranker: deterministic token-overlap scoring.

Used when CrossEncoder is unavailable (no GPU/memory, model download failure).
Unlike the ML-based reranker, this classifer requires no external dependencies
and always returns a valid score.

Architecture note: this module is intentionally isolated from container.py so
that adding type hints or imports in the container does not create circular
dependency risks.
"""

from __future__ import annotations

import logging
import time

from src.domain.schemas import Latency, RetrievalStatus
from src.retrieval.evidence_rerank import apply_score_threshold, select_final_contexts
from src.retrieval.relevance import (
    contains_requested_numeric_answer,
    corpus_lexical_relevance_scores,
    expects_numeric_answer,
)
from src.retrieval.reranker import BaseReranker, RerankerModelMetadata

logger = logging.getLogger(__name__)


class LexicalFallbackReranker(BaseReranker):
    """Deterministic fallback when the CrossEncoder cannot be loaded."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self.revision = "lexical-fallback"
        self.device = "cpu"
        self.backend = "lexical"
        self.batch_size = 1
        self.max_length = 512

    def load_model(self):
        return self

    def warmup_model(self) -> None:
        return None

    def rerank_batch(
        self,
        query: str,
        candidates,
    ) -> list[float]:
        if not set(query.split()):
            return [0.0] * len(candidates)
        scores = corpus_lexical_relevance_scores(
            query,
            [candidate.content for candidate in candidates],
            [candidate.metadata for candidate in candidates],
        )
        if expects_numeric_answer(query):
            scores = [
                score
                if contains_requested_numeric_answer(query, candidate.content)
                else 0.0
                for candidate, score in zip(candidates, scores, strict=True)
            ]
        return [
            score if candidate.content.strip() else 0.0
            for candidate, score in zip(candidates, scores, strict=True)
        ]

    def get_model_metadata(self) -> RerankerModelMetadata:
        return RerankerModelMetadata(
            model_name=self.model_name,
            revision=self.revision,
            device=self.device,
            backend=self.backend,
            batch_size=self.batch_size,
            max_length=self.max_length,
            loaded=True,
            warmed_up=True,
        )


class LexicalFallbackRerankerService:
    """Adapter that lets the workflow call the lexical fallback like a service."""

    def __init__(self, reranker: LexicalFallbackReranker):
        self.reranker = reranker

    async def rerank(self, request) -> RerankResult:  # noqa: F821
        from src.domain.schemas import RerankResult

        started = time.perf_counter()
        scores = self.reranker.rerank_batch(
            request.original_query, list(request.candidates)
        )
        scored = [
            candidate.model_copy(update={"rerank_score": float(score)})
            for candidate, score in zip(request.candidates, scores, strict=True)
        ]
        scored.sort(
            key=lambda candidate: (
                -float(candidate.rerank_score or 0.0),
                -candidate.fusion_score,
                candidate.chunk_id,
            )
        )
        logger.info(
            "lexical_reranker_top_candidates top=%s",
            [
                (candidate.chunk_id, round(float(candidate.rerank_score or 0.0), 3))
                for candidate in scored[:5]
            ],
        )
        selected = apply_score_threshold(scored, threshold=None)
        if not selected:
            return RerankResult(
                status=RetrievalStatus.NOT_FOUND,
                original_query=request.original_query,
                candidates=[],
                latency=Latency(total_ms=(time.perf_counter() - started) * 1000),
                warnings=["Lexical fallback reranker returned no candidates."],
            )
        selected = select_final_contexts(
            selected,
            final_limit=min(request.limit, 5),
            pre_diversity_limit=max(request.limit, 5),
            max_chunks_per_document=2,
        )
        return RerankResult(
            status=RetrievalStatus.PARTIAL,
            original_query=request.original_query,
            candidates=selected,
            latency=Latency(total_ms=(time.perf_counter() - started) * 1000),
            warnings=["Using lexical fallback reranker."],
        )


def build_lexical_fallback_reranker(model_name: str) -> LexicalFallbackRerankerService:
    return LexicalFallbackRerankerService(LexicalFallbackReranker(model_name=model_name))
