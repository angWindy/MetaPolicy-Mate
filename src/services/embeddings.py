from __future__ import annotations

import asyncio
import hashlib
import math
import re
from typing import Protocol

from src.rag.config import RAGSettings


class DenseEmbeddingProvider(Protocol):
    dimensions: int
    model_name: str
    model_version: str

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


EmbeddingProvider = DenseEmbeddingProvider


def content_hash_for_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def validate_embedding_dimension(vector: list[float], expected_dimensions: int) -> None:
    if len(vector) != expected_dimensions:
        raise ValueError(
            f"Embedding has {len(vector)} dimensions; expected {expected_dimensions}."
        )


class HashEmbeddingProvider:
    """Deterministic local embedding for tests and API demos without external calls."""

    def __init__(
        self,
        dimensions: int = 256,
        model_name: str = "hash-embedding",
        model_version: str = "test-v1",
    ):
        self.dimensions = dimensions
        self.model_name = model_name
        self.model_version = model_version

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", text.lower(), flags=re.UNICODE)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class OpenAIEmbeddingProvider:
    def __init__(self, settings: RAGSettings):
        from langchain_openai import OpenAIEmbeddings

        self.dimensions = settings.embedding_dimensions
        self.model_name = settings.embedding_model
        self.model_version = settings.embedding_version
        self.client = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
            dimensions=settings.embedding_dimensions,
            chunk_size=settings.embedding_batch_size,
        )

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        return await self.client.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self.client.aembed_query(text)


class SentenceTransformerEmbeddingProvider:
    def __init__(self, settings: RAGSettings):
        from sentence_transformers import SentenceTransformer

        self.model_name = settings.embedding_model
        self.model_version = settings.embedding_version
        self.batch_size = settings.embedding_batch_size
        self.model = SentenceTransformer(
            settings.embedding_model,
            device=settings.embedding_device,
        )
        get_dimensions = getattr(
            self.model,
            "get_embedding_dimension",
            self.model.get_sentence_embedding_dimension,
        )
        model_dimensions = get_dimensions()
        if model_dimensions is None:
            raise ValueError("Sentence Transformer did not report its embedding dimension.")
        self.dimensions = int(model_dimensions)
        if self.dimensions != settings.embedding_dimensions:
            raise ValueError(
                f"Configured embedding dimension is {settings.embedding_dimensions}, "
                f"but model {self.model_name} produces {self.dimensions}."
            )

    def _encode(self, texts: list[str]) -> list[list[float]]:
        encoded = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        values = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return [[float(value) for value in vector] for vector in values]

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        return await asyncio.to_thread(self._encode, texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


class GeminiEmbeddingProvider:
    def __init__(self, settings: RAGSettings):
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        self.model_name = settings.embedding_model or "gemini-embedding-001"
        self.model_version = settings.embedding_version
        self.client = GoogleGenerativeAIEmbeddings(
            model=self.model_name,
            google_api_key=settings.gemini_api_key,
            task_type="retrieval_document",
        )
        # Gemini returns 768-dim for text-embedding-001, 3072-dim for later models.
        # Override with actual dimension from first embedding to match vector store.
        self.dimensions: int | None = None

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        results = await asyncio.to_thread(self.client.embed_documents, texts)
        if self.dimensions is None and results:
            self.dimensions = len(results[0])
        return results

    async def embed_query(self, text: str) -> list[float]:
        result = await asyncio.to_thread(self.client.embed_query, text)
        if self.dimensions is None:
            self.dimensions = len(result)
        return result


class OllamaEmbeddingProvider:
    def __init__(self, settings: RAGSettings):
        from langchain_ollama import OllamaEmbeddings

        self.dimensions = settings.embedding_dimensions
        self.model_name = settings.embedding_model or "nomic-embed-text"
        self.model_version = settings.embedding_version
        self.client = OllamaEmbeddings(
            model=self.model_name,
            base_url=settings.ollama_base_url or "http://localhost:11434",
        )

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        return await asyncio.to_thread(self.client.embed_documents, texts)

    async def embed_query(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.client.embed_query, text)


class CachedDenseEmbeddingProvider:
    """Process-local content-hash cache; Redis is intentionally not required.

    Supports providers with dynamic dimensions (e.g., Gemini) that are only
    determined after the first embedding call.
    """

    def __init__(self, provider: DenseEmbeddingProvider):
        self.provider = provider
        # Use getattr to support providers with dynamic dimensions (e.g., GeminiEmbeddingProvider)
        self._dimensions: int | None = getattr(provider, "dimensions", None)
        self.model_name = provider.model_name
        self.model_version = provider.model_version
        self._document_cache: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    @property
    def dimensions(self) -> int:
        if self._dimensions is None:
            # Return configured fallback for lazy initialization (e.g., Gemini auto-detects on first call)
            return getattr(self.provider, "dimensions", 0) or 0
        return self._dimensions

    def _sync_dimensions(self, vector: list[float]) -> None:
        if self._dimensions is None:
            self._dimensions = len(vector)

    def _cache_key(self, content_hash: str) -> str:
        return f"{self.model_name}:{self.model_version}:{content_hash}"

    async def embed_query(self, text: str) -> list[float]:
        vector = await self.provider.embed_query(text)
        # Double-checked locking: fast-path without acquiring the lock when
        # dimensions are already initialised; re-check inside the lock to
        # avoid redundant work and guarantee a single initialiser.
        if self._dimensions is None:
            async with self._lock:
                if self._dimensions is None:
                    self._sync_dimensions(vector)
        return vector

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        if content_hashes is None:
            vectors = await self.provider.embed_documents(texts)
            if vectors and self._dimensions is None:
                async with self._lock:
                    if self._dimensions is None:
                        self._sync_dimensions(vectors[0])
            return vectors
        if len(texts) != len(content_hashes):
            raise ValueError("texts and content_hashes must have equal length.")
        if any(not content_hash.strip() for content_hash in content_hashes):
            raise ValueError("content_hash must not be blank.")

        missing: dict[str, str] = {}
        for text, content_hash in zip(texts, content_hashes, strict=True):
            key = self._cache_key(content_hash)
            if key not in self._document_cache and key not in missing:
                missing[key] = text

        if missing:
            vectors = await self.provider.embed_documents(list(missing.values()))
            if len(vectors) != len(missing):
                raise ValueError("Embedding provider returned an unexpected batch size.")
            if self._dimensions is None:
                async with self._lock:
                    if self._dimensions is None:
                        self._sync_dimensions(vectors[0])
            for key, vector in zip(missing, vectors, strict=True):
                self._document_cache[key] = vector
        return [
            self._document_cache[self._cache_key(content_hash)]
            for content_hash in content_hashes
        ]


def build_embedding_provider(settings: RAGSettings) -> DenseEmbeddingProvider:
    """Build the embedding pipeline: primary (cached) + optional resilient wrapper.

    For normal operation (no rate-limit handling), use `build_embedding_provider()`.
    For automatic retry + fallback, use `build_resilient_embedding_provider()`.
    """
    if settings.embedding_provider == "openai":
        provider: DenseEmbeddingProvider = OpenAIEmbeddingProvider(settings)
    elif settings.embedding_provider == "gemini":
        provider = _build_gemini_provider(settings)
    elif settings.embedding_provider == "sentence_transformers":
        provider = SentenceTransformerEmbeddingProvider(settings)
    elif settings.embedding_provider == "ollama":
        provider = OllamaEmbeddingProvider(settings)
    else:
        # "hash" or unknown
        provider = HashEmbeddingProvider(
            dimensions=settings.embedding_dimensions,
            model_name="hash-embedding",
            model_version="test-v1",
        )
    return CachedDenseEmbeddingProvider(provider)


def build_resilient_embedding_provider(settings: RAGSettings) -> DenseEmbeddingProvider:
    """Build embedding provider with retry + automatic fallback chain.

    Use this instead of build_embedding_provider when you want:
    - Exponential-backoff retry on rate limits (429) and transient errors.
    - Automatic fallback to sentence_transformers or hash if primary fails.
    """
    primary = build_embedding_provider(settings)
    cached = primary if isinstance(primary, CachedDenseEmbeddingProvider) else CachedDenseEmbeddingProvider(primary)
    return ResilientEmbeddingProvider(
        primary=cached,
        settings=settings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Resilient provider: retry + auto-fallback chain
# ─────────────────────────────────────────────────────────────────────────────


class ResilientEmbeddingProvider:
    """Embedding provider with retry + automatic fallback to local providers.

    On transient errors (rate limits, timeouts, 5xx) this provider:
    1. Retries with exponential backoff up to EMBEDDING_MAX_RETRIES times.
    2. If all retries exhausted, tries the next provider in the fallback chain.
    3. The last resort is always Hash (deterministic, no API key required).

    Fallback chain comes from EMBEDDING_FALLBACK_PROVIDERS in RAGSettings.
    """

    def __init__(
        self,
        primary: CachedDenseEmbeddingProvider,
        settings: RAGSettings,
    ):
        self._primary = primary
        self._settings = settings
        self._fallback_providers: list[CachedDenseEmbeddingProvider] = []
        self._fallback_providers = self._build_fallback_chain()
        self.model_name = primary.model_name
        self.model_version = primary.model_version
        self._dimensions: int | None = None

    @property
    def dimensions(self) -> int:
        if self._dimensions is not None:
            return self._dimensions
        return self._primary.dimensions

    def _build_fallback_chain(self) -> list[CachedDenseEmbeddingProvider]:
        """Build the ordered list of fallback providers from settings."""
        chain: list[CachedDenseEmbeddingProvider] = []
        for provider_name in self._settings.embedding_fallback_provider_list:
            try:
                provider = self._build_provider_by_name(provider_name)
                if provider is not None:
                    chain.append(provider)
            except Exception:  # noqa: BLE001
                # Skip providers that can't be initialized (missing key, etc.)
                pass
        return chain

    def _build_provider_by_name(
        self, provider_name: str
    ) -> CachedDenseEmbeddingProvider | None:
        """Build a single embedding provider by name (without going through settings)."""
        from src.services.embeddings import (
            CachedDenseEmbeddingProvider,
            HashEmbeddingProvider,
            OllamaEmbeddingProvider,
            OpenAIEmbeddingProvider,
            SentenceTransformerEmbeddingProvider,
        )

        if provider_name == "openai":
            return CachedDenseEmbeddingProvider(
                OpenAIEmbeddingProvider(self._settings)
            )
        if provider_name == "gemini":
            return CachedDenseEmbeddingProvider(
                _build_gemini_provider(self._settings)
            )
        if provider_name == "sentence_transformers":
            return CachedDenseEmbeddingProvider(
                SentenceTransformerEmbeddingProvider(self._settings)
            )
        if provider_name == "ollama":
            return CachedDenseEmbeddingProvider(
                OllamaEmbeddingProvider(self._settings)
            )
        if provider_name == "hash":
            return CachedDenseEmbeddingProvider(
                HashEmbeddingProvider(
                    dimensions=self._settings.embedding_dimensions,
                    model_name="hash-embedding",
                    model_version="fallback-v1",
                )
            )
        return None

    async def _call_embed_query(self, provider, text: str) -> list[float]:
        from src.services.retry_utils import is_retryable, with_retry

        return await with_retry(
            provider.embed_query,
            text,
            max_attempts=self._settings.embedding_max_retries,
            base_delay=self._settings.embedding_retry_base_delay,
            max_delay=self._settings.embedding_retry_max_delay,
        )

    async def _call_embed_documents(
        self, provider, texts: list[str], content_hashes: list[str] | None = None
    ) -> list[list[float]]:
        from src.services.retry_utils import is_retryable, with_retry

        return await with_retry(
            provider.embed_documents,
            texts,
            content_hashes=content_hashes,
            max_attempts=self._settings.embedding_max_retries,
            base_delay=self._settings.embedding_retry_base_delay,
            max_delay=self._settings.embedding_retry_max_delay,
        )

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed_query_with_fallback(text, start_fallback=0)

    async def _embed_query_with_fallback(
        self, text: str, start_fallback: int
    ) -> list[float]:
        """Try primary, then each fallback in order. Hash is always last."""
        all_providers = [self._primary] + self._fallback_providers

        for idx in range(start_fallback, len(all_providers)):
            provider = all_providers[idx]
            try:
                result = await self._call_embed_query(provider, text)
                if self._dimensions is None:
                    self._dimensions = len(result)
                return result
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "Embedding provider %s failed for embed_query (will fallback if available): %s: %s",
                    provider.model_name,
                    type(exc).__name__,
                    exc,
                )
                # Continue to next provider in chain
        raise RuntimeError(
            f"embed_query failed for all embedding providers "
            f"(primary={self._primary.model_name}, fallbacks="
            f"{[p.model_name for p in self._fallback_providers]})"
        )

    async def embed_documents(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None = None,
    ) -> list[list[float]]:
        return await self._embed_documents_with_fallback(
            texts, content_hashes=content_hashes, start_fallback=0
        )

    async def _embed_documents_with_fallback(
        self,
        texts: list[str],
        *,
        content_hashes: list[str] | None,
        start_fallback: int,
    ) -> list[list[float]]:
        """Try primary, then each fallback in order. Hash is always last."""
        all_providers = [self._primary] + self._fallback_providers

        for idx in range(start_fallback, len(all_providers)):
            provider = all_providers[idx]
            try:
                result = await self._call_embed_documents(
                    provider, texts, content_hashes=content_hashes
                )
                if self._dimensions is None:
                    self._dimensions = result[0] if result else 0
                return result
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "Embedding provider %s failed for embed_documents (will fallback if available): %s: %s",
                    provider.model_name,
                    type(exc).__name__,
                    exc,
                )
        raise RuntimeError(
            f"embed_documents failed for all embedding providers "
            f"(primary={self._primary.model_name}, fallbacks="
            f"{[p.model_name for p in self._fallback_providers]})"
        )


def _build_gemini_provider(settings: RAGSettings):
    """Build GeminiEmbeddingProvider inline to avoid circular import."""
    from src.services.embeddings import GeminiEmbeddingProvider

    return GeminiEmbeddingProvider(settings)

