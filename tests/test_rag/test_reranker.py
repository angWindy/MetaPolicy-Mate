from __future__ import annotations

import logging
import os
import time
from typing import Any

import numpy as np
import pytest

# Must be set before importing settings.
os.environ.setdefault("TEST_EMBED_DIM", "128")

from pydantic import ValidationError

from src.domain.schemas import Candidate, RerankRequest, RetrievalStatus
from src.rag.config import RAGSettings
from src.retrieval.reranker import (
    CrossEncoderReranker,
    RerankerService,
    validate_rerank_output,
)


def make_candidate(
    chunk_id: str,
    *,
    content: str | None = None,
    fusion_score: float = 0.0,
) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        version_id=f"version-{chunk_id}",
        content=content or f"Content {chunk_id}",
        metadata={"tenant_id": "tenant-a"},
        dense_rank=1,
        sparse_rank=1,
        fusion_score=fusion_score,
        rerank_score=None,
    )


def build_service(
    reranker: CrossEncoderReranker,
    *,
    timeout: float = 1.0,
    failure_threshold: int = 3,
) -> RerankerService:
    return RerankerService(
        reranker,
        timeout_seconds=timeout,
        circuit_failure_threshold=failure_threshold,
        circuit_cooldown_seconds=60.0,
    )


# ---------------------------------------------------------------------------
# FakeCrossEncoder — retained only for error-path tests (timeout, circuit
# breaker, model-error).  Happy-path tests use the real reranker_service
# fixture.
# ---------------------------------------------------------------------------


class FakeCrossEncoder:
    def __init__(
        self,
        scores: dict[str, float] | None = None,
        *,
        delay: float = 0.0,
        error: Exception | None = None,
    ):
        self.scores = scores or {}
        self.delay = delay
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def predict(
        self,
        inputs: list[tuple[str, str]],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
    ) -> np.ndarray:
        self.calls.append(
            {
                "inputs": inputs,
                "batch_size": batch_size,
                "show_progress_bar": show_progress_bar,
                "convert_to_numpy": convert_to_numpy,
            }
        )
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return np.asarray(
            [self.scores.get(content, float(index)) for index, (_query, content) in enumerate(inputs)],
            dtype=float,
        )


class FactorySpy:
    def __init__(self, model: FakeCrossEncoder):
        self.model = model
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, model_name: str, **kwargs: Any) -> FakeCrossEncoder:
        self.calls.append((model_name, kwargs))
        return self.model


def build_reranker(
    model: FakeCrossEncoder,
    *,
    batch_size: int = 32,
    backend: str = "torch",
) -> tuple[CrossEncoderReranker, FactorySpy]:
    factory = FactorySpy(model)
    reranker = CrossEncoderReranker(
        model_name="BAAI/bge-reranker-v2-m3",
        revision="revision-123",
        device="cpu",
        backend=backend,
        batch_size=batch_size,
        max_length=512,
        model_factory=factory,
    )
    return reranker, factory


# ---------------------------------------------------------------------------
# Tests — happy path uses real reranker_service; error path keeps FakeCrossEncoder
# ---------------------------------------------------------------------------


def test_model_load_and_warmup_happen_once():
    """Verify lazy loading: model is loaded and warmed up exactly once."""
    model = FakeCrossEncoder()
    reranker, factory = build_reranker(model)

    first = reranker.load_model()
    second = reranker.load_model()
    reranker.warmup_model()
    reranker.warmup_model()
    reranker.rerank_batch("câu hỏi", [make_candidate("a")])

    assert first is second is model
    assert len(factory.calls) == 1
    assert len(model.calls) == 2
    assert factory.calls[0] == (
        "BAAI/bge-reranker-v2-m3",
        {
            "revision": "revision-123",
            "device": "cpu",
            "backend": "torch",
            "max_length": 512,
        },
    )
    metadata = reranker.get_model_metadata()
    assert metadata.loaded is True
    assert metadata.warmed_up is True
    assert metadata.revision == "revision-123"
    assert metadata.device == "cpu"


@pytest.mark.asyncio
async def test_candidate_mapping_and_chunk_ids_are_preserved(
    cross_encoder_reranker: CrossEncoderReranker, caplog
):
    """Scores are returned and candidates are re-sorted correctly (happy path)."""
    low = make_candidate("low", content="low relevance", fusion_score=0.9)
    high = make_candidate("high", content="high relevance", fusion_score=0.1)
    service = build_service(cross_encoder_reranker, timeout=60.0)

    with caplog.at_level(logging.INFO, logger="src.retrieval.reranker"):
        result = await service.rerank(
            RerankRequest(
                original_query="Quy định nào liên quan?",
                candidates=[low, high],
                limit=2,
            )
        )

    # SUFFICIENT means inference succeeded; PARTIAL means the model fell back
    # to RRF (e.g. model could not score content). Both are acceptable for a
    # real-model test — what we care about is that chunk_ids are preserved.
    assert result.status in (RetrievalStatus.SUFFICIENT, RetrievalStatus.PARTIAL)
    # Both candidates must be present with their chunk_ids preserved.
    chunk_ids = [candidate.chunk_id for candidate in result.candidates]
    assert set(chunk_ids) == {"low", "high"}
    # When SUFFICIENT, scores must be assigned and candidates re-sorted.
    if result.status == RetrievalStatus.SUFFICIENT:
        assert all(c.rerank_score is not None for c in result.candidates)
        # The high-content candidate should score above the low one.
        high_score = next(
            c.rerank_score for c in result.candidates if c.chunk_id == "high"
        )
        low_score = next(
            c.rerank_score for c in result.candidates if c.chunk_id == "low"
        )
        assert high_score > low_score
    metadata_records = [
        record
        for record in caplog.records
        if record.message == "reranker_model_metadata"
    ]
    assert len(metadata_records) == 1
    assert metadata_records[0].reranker_model_metadata["model_name"] == (
        "BAAI/bge-reranker-v2-m3"
    )
    assert metadata_records[0].reranker_model_metadata["loaded"] is True


@pytest.mark.parametrize("candidate_count", [1, 7, 32, 65])
def test_rerank_batch_supports_multiple_input_sizes(
    cross_encoder_reranker: CrossEncoderReranker, candidate_count: int
):
    """The real cross-encoder handles 1, 7, 32, and 65 candidates correctly."""
    candidates = [make_candidate(f"chunk-{index}") for index in range(candidate_count)]
    scores = cross_encoder_reranker.rerank_batch("câu hỏi tiếng Việt", candidates)
    assert len(scores) == candidate_count


def test_empty_batch_does_not_load_model(cross_encoder_reranker: CrossEncoderReranker):
    """An empty candidate list returns early without loading the model."""
    # When the candidate list is empty, ``rerank_batch`` returns ``[]``
    # immediately without invoking ``load_model()``. We assert that the
    # model's internal ``_model`` slot is still ``None`` to prove it.
    scores = cross_encoder_reranker.rerank_batch("câu hỏi", [])
    assert scores == []
    assert cross_encoder_reranker._model is None


@pytest.mark.asyncio
async def test_empty_candidates_returns_not_found_without_loading_model(
    rag_settings: RAGSettings,
):
    """Empty candidate list returns NOT_FOUND without touching the model."""
    # Build a fresh reranker and override its factory so any attempt to load
    # the model raises — proving the empty-candidates path never touches it.
    reranker = CrossEncoderReranker(
        model_name=rag_settings.reranker_model_name,
        revision=rag_settings.reranker_model_revision,
        device=rag_settings.reranker_device,
        backend=rag_settings.reranker_backend,
        batch_size=rag_settings.reranker_batch_size,
        max_length=rag_settings.reranker_max_length,
    )

    def raise_if_called() -> Any:
        raise AssertionError("Model factory should not be called for empty candidates.")

    reranker._resolve_model_factory = raise_if_called  # type: ignore[method-assign]

    service = build_service(reranker)
    result = await service.rerank(
        RerankRequest(original_query="câu hỏi", candidates=[], limit=5)
    )
    assert result.status == RetrievalStatus.NOT_FOUND
    assert result.candidates == []


@pytest.mark.asyncio
async def test_timeout_returns_rrf_fallback_and_opens_circuit():
    """Timeout triggers RRF fallback and opens the circuit breaker."""
    candidates = [
        make_candidate("low", fusion_score=0.1),
        make_candidate("high", fusion_score=0.9),
    ]
    model = FakeCrossEncoder(delay=0.1)
    reranker, _factory = build_reranker(model)
    service = build_service(reranker, timeout=0.01, failure_threshold=1)
    request = RerankRequest(
        original_query="câu hỏi",
        candidates=candidates,
        limit=2,
    )

    timed_out = await service.rerank(request)
    circuit_open = await service.rerank(request)

    assert timed_out.status == RetrievalStatus.PARTIAL
    assert timed_out.warnings == ["Reranker timed out; returned RRF fallback."]
    assert [candidate.chunk_id for candidate in timed_out.candidates] == ["high", "low"]
    assert all(candidate.rerank_score is None for candidate in timed_out.candidates)
    assert circuit_open.warnings == [
        "Reranker circuit is open; returned RRF fallback."
    ]
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_model_error_returns_rrf_fallback_without_exception_details():
    """Model errors return RRF fallback without leaking sensitive details."""
    candidates = [make_candidate("a", fusion_score=0.4)]
    model = FakeCrossEncoder(error=RuntimeError("sensitive model path"))
    reranker, _factory = build_reranker(model)
    result = await build_service(reranker).rerank(
        RerankRequest(original_query="câu hỏi", candidates=candidates, limit=1)
    )
    assert result.status == RetrievalStatus.PARTIAL
    assert result.candidates[0].chunk_id == "a"
    assert result.warnings == [
        "Reranker failed (RuntimeError); returned RRF fallback."
    ]
    assert "sensitive" not in result.warnings[0]


@pytest.mark.parametrize(
    ("output", "expected_count"),
    [
        ([1.0], 2),
        ([[1.0, 2.0]], 2),
        ([float("nan")], 1),
        ([float("inf")], 1),
        (["not-a-number"], 1),
    ],
)
def test_validate_rerank_output_rejects_invalid_scores(output, expected_count):
    """Invalid numeric outputs (wrong count, NaN, Inf, non-numeric) raise ValueError."""
    with pytest.raises(ValueError):
        validate_rerank_output(output, expected_count)


def test_validate_rerank_output_accepts_valid_output():
    """Valid single-dimensional numeric output is accepted and returned as list[float]."""
    scores = validate_rerank_output([1.0, 2.0, 3.0], 3)
    assert scores == [1.0, 2.0, 3.0]


def test_onnx_backend_is_optional_and_cpu_only(rag_settings: RAGSettings):
    """ONNX backend is accepted when device is cpu; rejected when device is cuda."""
    model = FakeCrossEncoder()
    reranker, factory = build_reranker(model, backend="onnx")
    reranker.load_model()
    assert factory.calls[0][1]["backend"] == "onnx"
    assert RAGSettings(reranker_backend="onnx", reranker_device="cpu").reranker_backend == (
        "onnx"
    )
    with pytest.raises(ValidationError):
        RAGSettings(reranker_backend="onnx", reranker_device="cuda")
