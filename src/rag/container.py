from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from src.db.repository import Repository
from src.db.session import Database
from src.domain.schemas import (
    QdrantPayload,
)
from src.ingestion.parser import DocumentParser
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.worker import IngestionWorker
from src.rag.config import RAGSettings, get_rag_settings
from src.rag.generator import AnswerGenerator, build_answer_generator
from src.rag.pipeline import RAGPipeline
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.reranker import (
    BaseReranker,
    build_reranker_service,
)
from src.retrieval.sparse import SparseRetriever
from src.retrieval.vector_store import VectorRecord, VectorStore, build_vector_store
from src.services.embeddings import (
    EmbeddingProvider,
    build_resilient_embedding_provider,
    content_hash_for_text,
)
from src.services.llm_factory import build_llm
from src.services.sparse_embeddings import (
    SparseEmbeddingProvider,
    build_sparse_embedding_provider,
)
from src.services.storage import LocalDocumentStorage

logger = logging.getLogger(__name__)

_ACCESS_LEVEL_TO_CLASSIFICATION = {
    "public": "public",
    "internal": "internal",
    "department": "internal",
    "restricted": "restricted",
}


def _map_access_level_to_classification(access_level: str) -> str:
    return _ACCESS_LEVEL_TO_CLASSIFICATION.get(access_level, "internal")


def _build_qdrant_payload(
    *,
    chunk_metadata: dict,
    document,
    version,
    embeddings: EmbeddingProvider,
    status: str,
    index_version: str,
) -> dict:
    """Build a Qdrant payload that satisfies the build_access_filter contract."""
    classification = _map_access_level_to_classification(
        getattr(document, "access_level", "internal")
    )
    allowed_units = [
        item.upper() for item in (document.allowed_departments or [])
    ] or ["*"]
    payload = QdrantPayload(
        chunk_id=chunk_metadata.get("chunk_id") or chunk_metadata.get("id") or "",
        document_id=document.id,
        version_id=version.id,
        tenant_id=chunk_metadata.get(
            "tenant_id", (version.metadata_json or {}).get("tenant_id", "hust")
        ),
        status=status,
        legal_status=version.legal_status,
        classification=classification,
        allowed_roles=["*"],
        allowed_units=allowed_units,
        valid_from=version.effective_from.isoformat() if version.effective_from else None,
        valid_to=version.effective_to.isoformat() if version.effective_to else None,
        page=chunk_metadata.get("page"),
        section=chunk_metadata.get("section") or chunk_metadata.get("heading"),
        embedding_model=embeddings.model_name,
        embedding_version=embeddings.model_version,
        content_hash=chunk_metadata.get("content_hash"),
        index_version=index_version,
        metadata={k: v for k, v in chunk_metadata.items() if k not in {
            "tenant_id", "status", "legal_status", "classification",
            "allowed_roles", "allowed_units", "valid_from", "valid_to",
            "embedding_model", "embedding_version", "content_hash",
            "index_version", "chunk_id",
        }},
    )
    return payload.model_dump(mode="json")


class _LexicalFallbackReranker(BaseReranker):
    """Deterministic fallback when the CrossEncoder cannot be loaded.

    DEPRECATED: Moved to src/retrieval/lexical_reranker.py.
    This local copy exists only to avoid breaking existing imports; prefer
    importing from src/retrieval/lexical_reranker.py in new code.
    """
    # Proxy to the canonical implementation
    _canonical: type | None = None

    def __init__(self, model_name: str):
        from src.retrieval.lexical_reranker import LexicalFallbackReranker as Canonical
        self._impl = Canonical(model_name)
        # Expose same attributes for backward compatibility
        self.model_name = self._impl.model_name
        self.revision = self._impl.revision
        self.device = self._impl.device
        self.backend = self._impl.backend
        self.batch_size = self._impl.batch_size
        self.max_length = self._impl.max_length

    def load_model(self): return self._impl.load_model()
    def warmup_model(self) -> None: return self._impl.warmup_model()
    def rerank_batch(self, query: str, candidates=None):
        return self._impl.rerank_batch(query, candidates)
    def get_model_metadata(self):
        return self._impl.get_model_metadata()


class _LexicalFallbackService:
    """Adapter that lets the workflow call the lexical fallback like a service.

    DEPRECATED: Moved to src/retrieval/lexical_reranker.py.
    """
    def __init__(self, reranker: _LexicalFallbackReranker):
        from src.retrieval.lexical_reranker import LexicalFallbackRerankerService
        self._impl = LexicalFallbackRerankerService(reranker._impl)

    async def rerank(self, request):
        return await self._impl.rerank(request)


def _build_reranker(settings: RAGSettings):
    """Build the reranker service according to settings.reranker_provider."""
    if settings.reranker_provider == "lexical_fallback":
        logger.info("reranker_provider=lexical_fallback configured by user.")
        return _LexicalFallbackService(
            _LexicalFallbackReranker(model_name=settings.reranker_model_name)
        )
    try:
        service = build_reranker_service(settings)
        # Eagerly load and warm the model to surface failures early.
        service.reranker.load_model()
        service.reranker.warmup_model()
        logger.info(
            "reranker_provider=cross_encoder loaded model=%s",
            settings.reranker_model_name,
        )
        return service
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "reranker_unavailable provider=cross_encoder model=%s reason=%s; "
            "falling back to lexical reranker.",
            settings.reranker_model_name,
            type(exc).__name__,
        )
        return _LexicalFallbackService(
            _LexicalFallbackReranker(model_name=settings.reranker_model_name)
        )


class RAGContainer:
    """Composition root for the standalone RAG and database module."""

    def __init__(self, settings: RAGSettings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.parsed_documents_dir.mkdir(parents=True, exist_ok=True)
        self.database = Database(settings)
        self.database.create_all()
        self.repository = Repository(self.database.session_factory)
        self.embeddings: EmbeddingProvider = build_resilient_embedding_provider(settings)
        self.vector_store: VectorStore = build_vector_store(settings, self.embeddings.dimensions)
        self.sparse_provider: SparseEmbeddingProvider = build_sparse_embedding_provider(settings)
        self.storage = LocalDocumentStorage(settings.raw_documents_dir, settings.quarantine_dir)
        self.parser = DocumentParser(
            parser_backend=settings.parser_backend,
            docling_enabled=settings.docling_enabled,
            ocr_enabled=settings.ocr_enabled,
            min_ocr_confidence=settings.ocr_min_confidence,
            ocr_languages=settings.ocr_languages_list,
            ocr_gpu=settings.ocr_gpu,
            ocr_batch_size=settings.ocr_batch_size,
            ocr_workers=settings.ocr_workers,
            ocr_low_confidence_threshold=settings.ocr_low_confidence_threshold,
            preprocess_mode=settings.preprocess_mode,
            preprocess_dpi=settings.preprocess_dpi,
            preprocess_binary_threshold=settings.preprocess_binary_threshold,
            preprocess_denoise=settings.preprocess_denoise,
            preprocess_sharpen=settings.preprocess_sharpen,
            detect_tables=settings.detect_tables,
            vlm_enabled=settings.vlm_enabled,
            vlm_review_threshold=settings.vlm_review_threshold,
            ocr_engine_type=settings.ocr_engine,
            use_pp_structure=settings.use_pp_structure,
            pp_structure_text_det_limit_side_len=settings.pp_structure_text_det_limit_side_len,
            pp_structure_layout_threshold=settings.pp_structure_layout_threshold,
        )
        self.sparse_retriever = SparseRetriever(
            embedding_provider=self.sparse_provider,
            vector_store=self.vector_store,
            content_provider=self.repository,
        )
        self.generator: AnswerGenerator = build_answer_generator(settings)
        self.ingestion = IngestionPipeline(
            settings,
            self.repository,
            self.parser,
            self.storage,
            self.embeddings,
            self.vector_store,
            self.sparse_provider,
        )
        self.worker = IngestionWorker(self.ingestion, self.repository)
        self.retriever = HybridRetriever(
            settings,
            self.repository,
            self.embeddings,
            self.vector_store,
            self.sparse_retriever,
        )
        self.reranker_service = _build_reranker(settings)
        # Build a separate, lightweight LLM for HyDE so the (more expensive)
        # structured-output generator isn't reused for passage generation.
        # Falls back to None when the provider is `template` (no API key),
        # which disables HyDE for that environment.
        self.hyde_llm = _build_hyde_llm(settings)
        self.pipeline = RAGPipeline(
            settings,
            self.retriever,
            self.generator,
            reranker_service=self.reranker_service,
            hyde_llm=self.hyde_llm,
        )

    async def warm_index(self) -> int:
        items = self.repository.list_published_chunks_for_index()
        if not items:
            return 0
        # Build payload indexes once (idempotent; Qdrant only).
        if hasattr(self.vector_store, "create_payload_indexes"):
            await self.vector_store.create_payload_indexes()
        content_hashes = [
            item["payload"].get("content_hash")
            or content_hash_for_text(item["embedding_text"])
            for item in items
        ]
        vectors = await self.embeddings.embed_documents(
            [item["embedding_text"] for item in items],
            content_hashes=content_hashes,
        )
        sparse_vectors = self.sparse_provider.sparse_embed_documents(
            [item["embedding_text"] for item in items]
        )
        index_version = self.settings.qdrant_collection
        records = []
        for item, vector, sparse, content_hash in zip(
            items,
            vectors,
            sparse_vectors,
            content_hashes,
            strict=True,
        ):
            payload = item["payload"]
            payload["tenant_id"] = payload.get("tenant_id", "hust")
            payload["status"] = "published"
            payload["legal_status"] = payload.get("legal_status", "effective")
            payload["classification"] = payload.get("classification", "internal")
            payload["allowed_roles"] = payload.get("allowed_roles") or ["*"]
            payload["allowed_units"] = payload.get("allowed_units") or ["*"]
            payload["valid_from"] = (
                payload.get("effective_from")
                or payload.get("valid_from")
                or "1970-01-01T00:00:00Z"
            )
            payload["valid_to"] = payload.get("effective_to") or payload.get("valid_to")
            payload["chunk_id"] = item["id"]
            payload["content_hash"] = content_hash
            payload["embedding_model"] = self.embeddings.model_name
            payload["embedding_version"] = self.embeddings.model_version
            payload["sparse_model"] = self.sparse_provider.model_name
            payload["sparse_version"] = self.sparse_provider.model_version
            payload["sparse_vector"] = {
                "indices": list(sparse.indices),
                "values": list(sparse.values),
            }
            payload["index_version"] = index_version
            records.append(VectorRecord(id=item["id"], vector=vector, payload=payload))
        await self.vector_store.upsert(records)
        return len(records)


def _build_hyde_llm(settings: RAGSettings) -> Any | None:
    """Build a lightweight LLM for HyDE passage generation.

    Returns None when the provider is `template` (no API key) or when
    HYDE_ENABLED=false, so the downstream workflow gracefully skips HyDE.
    """
    if not settings.hyde_enabled:
        return None
    if settings.generator_provider == "template":
        logger.debug("HyDE disabled: generator_provider=template (no API key)")
        return None
    try:
        llm = build_llm(settings)
        # Verify the LLM is usable by doing a single async call against the
        # provider (the actual passage generation happens inside the graph).
        logger.info(
            "HyDE enabled with provider=%s model=%s",
            settings.generator_provider,
            settings.model_name,
        )
        return llm
    except Exception as exc:
        logger.warning("HyDE LLM build failed (HyDE will be disabled): %s", exc)
        return None


@lru_cache
def get_rag_container() -> RAGContainer:
    return RAGContainer(get_rag_settings())


def reset_rag_container() -> None:
    get_rag_container.cache_clear()
