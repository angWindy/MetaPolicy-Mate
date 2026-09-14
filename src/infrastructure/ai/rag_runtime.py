import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from src.rag.config import (
    RAGSettings,
    get_rag_settings,
)
from src.rag.generator import (
    AnswerGenerator,
    build_answer_generator,
)
from src.retrieval.lexical_reranker import (
    build_lexical_fallback_reranker,
)
from src.retrieval.reranker import (
    build_reranker_service,
)
from src.retrieval.vector_store import (
    VectorStore,
    build_vector_store,
)
from src.services.embeddings import (
    EmbeddingProvider,
    build_resilient_embedding_provider,
)
from src.services.llm_factory import (
    build_llm,
)
from src.services.sparse_embeddings import (
    SparseEmbeddingProvider,
    build_sparse_embedding_provider,
)


logger = logging.getLogger(
    __name__
)


@dataclass(frozen=True)
class P234RagRuntime:
    settings: RAGSettings

    embeddings: EmbeddingProvider

    sparse_provider: (
        SparseEmbeddingProvider
    )

    vector_store: VectorStore

    generator: AnswerGenerator

    reranker_service: Any

    hyde_llm: Any | None


def _build_p234_reranker(
    settings: RAGSettings,
):
    if (
        settings.reranker_provider
        == "lexical_fallback"
    ):
        return (
            build_lexical_fallback_reranker(
                settings
                .reranker_model_name
            )
        )

    try:
        service = (
            build_reranker_service(
                settings
            )
        )

        service.reranker.load_model()

        service.reranker.warmup_model()

        return service

    except Exception as exc:
        logger.warning(
            "Reranker unavailable; "
            "using lexical fallback: %s",
            type(exc).__name__,
        )

        return (
            build_lexical_fallback_reranker(
                settings
                .reranker_model_name
            )
        )


def _build_p234_hyde_llm(
    settings: RAGSettings,
):
    if not settings.hyde_enabled:
        return None

    if (
        settings.generator_provider
        == "template"
    ):
        return None

    try:
        return build_llm(
            settings
        )

    except Exception as exc:
        logger.warning(
            "HyDE LLM unavailable: %s",
            type(exc).__name__,
        )

        return None


@lru_cache
def get_p234_rag_runtime(
) -> P234RagRuntime:
    settings = (
        get_rag_settings()
    )

    embeddings = (
        build_resilient_embedding_provider(
            settings
        )
    )

    sparse_provider = (
        build_sparse_embedding_provider(
            settings
        )
    )

    vector_store = (
        build_vector_store(
            settings,
            embeddings.dimensions,
        )
    )

    generator = (
        build_answer_generator(
            settings
        )
    )

    reranker_service = (
        _build_p234_reranker(
            settings
        )
    )

    hyde_llm = (
        _build_p234_hyde_llm(
            settings
        )
    )

    return P234RagRuntime(
        settings=settings,
        embeddings=embeddings,
        sparse_provider=(
            sparse_provider
        ),
        vector_store=(
            vector_store
        ),
        generator=generator,
        reranker_service=(
            reranker_service
        ),
        hyde_llm=hyde_llm,
    )