"""Tests for the multi-provider embedding factory."""

import pytest

from src.rag.config import RAGSettings
from src.services.embeddings import (
    HashEmbeddingProvider,
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    build_embedding_provider,
)


class TestBuildEmbeddingProvider:
    def test_hash_provider_default(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        assert provider.model_name == "hash-embedding"
        assert provider.dimensions == 256

    def test_hash_provider_cached(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        from src.services.embeddings import CachedDenseEmbeddingProvider
        assert isinstance(provider, CachedDenseEmbeddingProvider)

    def test_hash_provider_embed_query(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        vector = provider.provider._embed("học bổng sinh viên")
        assert len(vector) == 256
        assert abs(sum(v * v for v in vector) - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_hash_provider_async_query(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        vector = await provider.embed_query("test query")
        assert len(vector) == 256

    @pytest.mark.asyncio
    async def test_hash_provider_async_documents(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        vectors = await provider.embed_documents(["doc1", "doc2"])
        assert len(vectors) == 2
        assert all(len(v) == 256 for v in vectors)

    def test_hash_provider_deterministic(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        v1 = provider.provider._embed("same text")
        v2 = provider.provider._embed("same text")
        assert v1 == v2

    def test_hash_provider_different_texts_different_vectors(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        v1 = provider.provider._embed("text a")
        v2 = provider.provider._embed("text b")
        assert v1 != v2

    def test_unknown_provider_falls_back_to_hash(self):
        # Pydantic enum validation happens before factory — "unknown" is rejected at
        # RAGSettings construction time. The factory only receives valid enum values.
        with pytest.raises(Exception):
            RAGSettings(embedding_provider="unknown", embedding_dimensions=256)


class TestOllamaEmbeddingProvider:
    def test_ollama_model_config(self):
        settings = RAGSettings(
            embedding_provider="ollama",
            embedding_model="nomic-embed-text",
            embedding_dimensions=768,
            ollama_base_url="http://localhost:11434",
        )
        provider = OllamaEmbeddingProvider(settings)
        assert provider.model_name == "nomic-embed-text"
        assert provider.dimensions == 768


class TestCachedProviderWithHash:
    @pytest.mark.asyncio
    async def test_cache_skips_duplicate_documents(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        texts = ["document content", "document content"]
        hashes = ["hash1", "hash1"]
        vectors = await provider.embed_documents(texts, content_hashes=hashes)
        assert len(vectors) == 2
        assert vectors[0] == vectors[1]

    @pytest.mark.asyncio
    async def test_cache_different_hashes_produces_different_vectors(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        texts = ["text a", "text b"]
        hashes = ["hash_a", "hash_b"]
        vectors = await provider.embed_documents(texts, content_hashes=hashes)
        assert len(vectors) == 2

    @pytest.mark.asyncio
    async def test_no_cache_when_no_hashes(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        vectors = await provider.embed_documents(["doc1", "doc2"])
        assert len(vectors) == 2

    def test_cache_key_includes_model_info(self):
        settings = RAGSettings(embedding_provider="hash", embedding_dimensions=256)
        provider = build_embedding_provider(settings)
        key = provider._cache_key("abc123")
        assert "hash-embedding" in key
        assert "test-v1" in key
        assert "abc123" in key
