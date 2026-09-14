from __future__ import annotations

import uuid
from typing import Any

from src.domain.schemas import Latency, RerankRequest, RerankResult, RetrievalStatus
from src.rag.config import RAGSettings
from src.rag.generator import AnswerGenerator
from src.rag.state import RAGState
from src.rag.workflow import RetrievalWorkflow
from src.retrieval.hybrid import HybridRetriever


class _DefaultReranker:
    """Deterministic adapter that still executes the mandatory rerank node."""

    async def rerank(self, request: RerankRequest) -> RerankResult:
        ranked = sorted(
            request.candidates,
            key=lambda candidate: (
                -(
                    candidate.rerank_score
                    if candidate.rerank_score is not None
                    else candidate.fusion_score
                ),
                candidate.chunk_id,
            ),
        )[: request.limit]
        return RerankResult(
            status=RetrievalStatus.SUFFICIENT if ranked else RetrievalStatus.NOT_FOUND,
            original_query=request.original_query,
            candidates=ranked,
            latency=Latency(total_ms=0.0),
        )


class RAGPipeline:
    """Compatibility facade backed exclusively by the fixed RetrievalWorkflow."""

    def __init__(
        self,
        settings: RAGSettings,
        retriever: HybridRetriever,
        generator: AnswerGenerator,
        reranker_service: Any = None,
        hyde_llm: Any = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.generator = generator
        self.workflow = RetrievalWorkflow(
            settings=settings,
            retriever=retriever,
            reranker_service=reranker_service or _DefaultReranker(),
            generator=generator,
            context_provider=retriever.repository,
            hyde_llm=hyde_llm,
        )
        self.graph = self.workflow.graph

    async def ainvoke(
        self,
        state: RAGState,
        config: dict[str, Any] | None = None,
    ) -> RAGState:
        if config is None:
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
        return await self.workflow.ainvoke(state, config)


# Re-export so tests can import _DefaultReranker if needed.
__all__ = ["RAGPipeline", "_DefaultReranker"]
