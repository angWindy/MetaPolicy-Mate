from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from src.domain.schemas import (
    Candidate,
    Latency,
    RerankRequest,
    RerankResult,
    RetrievalStatus,
)
from src.rag.config import RAGSettings
from src.retrieval.rerank_cache import get_rerank_cache

logger = logging.getLogger(__name__)


class RerankerModelMetadata(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "model_name": "BAAI/bge-reranker-v2-m3",
                    "revision": "ef6343e0838fa68e275959461b0140b39f264eb0",
                    "device": "cpu",
                    "backend": "torch",
                    "batch_size": 32,
                    "max_length": 512,
                    "loaded": True,
                    "warmed_up": True,
                }
            ]
        }
    )

    model_name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    device: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    batch_size: int = Field(ge=1)
    max_length: int = Field(ge=1)
    loaded: bool
    warmed_up: bool


class CrossEncoderModel(Protocol):
    def predict(
        self,
        inputs: list[tuple[str, str]],
        *,
        batch_size: int,
        show_progress_bar: bool,
        convert_to_numpy: bool,
    ) -> Any: ...


ModelFactory = Callable[..., CrossEncoderModel]


def validate_rerank_output(output: Any, expected_count: int) -> list[float]:
    if expected_count < 0:
        raise ValueError("expected_count must not be negative.")
    try:
        scores = np.asarray(output, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Reranker output must be numeric.") from exc
    if scores.ndim == 0:
        scores = scores.reshape(1)
    elif scores.ndim == 2 and scores.shape[1] == 1:
        scores = scores.reshape(-1)
    elif scores.ndim != 1:
        raise ValueError("Reranker output must contain one score per pair.")
    if len(scores) != expected_count:
        raise ValueError(
            f"Reranker returned {len(scores)} scores for {expected_count} pairs."
        )
    if not np.isfinite(scores).all():
        raise ValueError("Reranker output contains a non-finite score.")
    return [float(score) for score in scores]


class BaseReranker(ABC):
    @abstractmethod
    def load_model(self) -> CrossEncoderModel: ...

    @abstractmethod
    def warmup_model(self) -> None: ...

    @abstractmethod
    def rerank_batch(
        self,
        query: str,
        candidates: Sequence[Candidate],
    ) -> list[float]: ...

    @abstractmethod
    def get_model_metadata(self) -> RerankerModelMetadata: ...


class CrossEncoderReranker(BaseReranker):
    """Lazy, load-once Sentence Transformers CrossEncoder adapter."""

    def __init__(
        self,
        *,
        model_name: str,
        revision: str,
        device: str,
        backend: str = "torch",
        batch_size: int = 32,
        max_length: int = 512,
        model_factory: ModelFactory | None = None,
    ):
        if not model_name.strip() or not revision.strip() or not device.strip():
            raise ValueError("Reranker model name, revision and device are required.")
        if backend not in {"torch", "onnx"}:
            raise ValueError("Reranker backend must be 'torch' or 'onnx'.")
        if batch_size < 1:
            raise ValueError("Reranker batch_size must be positive.")
        if max_length < 1:
            raise ValueError("Reranker max_length must be positive.")
        self.model_name = model_name
        self.revision = revision
        self.device = device
        self.backend = backend
        self.batch_size = batch_size
        self.max_length = max_length
        self._model_factory = model_factory
        self._model: CrossEncoderModel | None = None
        self._loaded = False
        self._warmed_up = False
        self._load_lock = threading.Lock()
        self._warmup_lock = threading.Lock()

    def _resolve_model_factory(self) -> ModelFactory:
        if self._model_factory is not None:
            return self._model_factory
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for CrossEncoder reranking."
            ) from exc
        return CrossEncoder

    def load_model(self) -> CrossEncoderModel:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is None:
                factory = self._resolve_model_factory()
                self._model = factory(
                    self.model_name,
                    revision=self.revision,
                    device=self.device,
                    backend=self.backend,
                    max_length=self.max_length,
                )
                self._loaded = True
        return self._model

    def warmup_model(self) -> None:
        if self._warmed_up:
            return
        with self._warmup_lock:
            if self._warmed_up:
                return
            model = self.load_model()
            output = model.predict(
                [("Quy định này áp dụng cho ai?", "Điều 1. Phạm vi áp dụng.")],
                batch_size=1,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            validate_rerank_output(output, 1)
            self._warmed_up = True

    def rerank_batch(
        self,
        query: str,
        candidates: Sequence[Candidate],
    ) -> list[float]:
        if not query.strip():
            raise ValueError("Rerank query must not be blank.")
        if not candidates:
            return []
        pairs = [(query, candidate.content) for candidate in candidates]
        model = self.load_model()
        output = model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return validate_rerank_output(output, len(candidates))

    def get_model_metadata(self) -> RerankerModelMetadata:
        return RerankerModelMetadata(
            model_name=self.model_name,
            revision=self.revision,
            device=self.device,
            backend=self.backend,
            batch_size=self.batch_size,
            max_length=self.max_length,
            loaded=self._loaded,
            warmed_up=self._warmed_up,
        )


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive.")
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive.")
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._open_until = 0.0
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        with self._lock:
            if self._open_until == 0.0:
                return True
            if time.monotonic() >= self._open_until:
                self._open_until = 0.0
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open_until = time.monotonic() + self.cooldown_seconds


class RerankerService:
    def __init__(
        self,
        reranker: BaseReranker,
        *,
        timeout_seconds: float,
        circuit_failure_threshold: int,
        circuit_cooldown_seconds: float,
        cache_enabled: bool = True,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.reranker = reranker
        self.timeout_seconds = timeout_seconds
        self.cache_enabled = cache_enabled
        self._cache = get_rerank_cache() if cache_enabled else None
        self.circuit_breaker = CircuitBreaker(
            circuit_failure_threshold,
            circuit_cooldown_seconds,
        )

    def _log_model_metadata(self) -> None:
        logger.info(
            "reranker_model_metadata",
            extra={
                "reranker_model_metadata": self.reranker.get_model_metadata().model_dump(
                    mode="json"
                )
            },
        )

    @staticmethod
    def _rrf_fallback(candidates: Sequence[Candidate], limit: int) -> list[Candidate]:
        indexed = list(enumerate(candidates))
        indexed.sort(key=lambda item: (-item[1].fusion_score, item[0]))
        return [
            candidate.model_copy(update={"rerank_score": None})
            for _index, candidate in indexed[:limit]
        ]

    @staticmethod
    def _result(
        request: RerankRequest,
        *,
        candidates: list[Candidate],
        status: RetrievalStatus,
        warnings: list[str],
        elapsed_ms: float,
    ) -> RerankResult:
        return RerankResult(
            status=status,
            original_query=request.original_query,
            candidates=candidates,
            warnings=warnings,
            latency=Latency(rerank_ms=elapsed_ms, total_ms=elapsed_ms),
        )

    async def rerank(self, request: RerankRequest) -> RerankResult:
        started = time.perf_counter()
        if not request.candidates:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return self._result(
                request,
                candidates=[],
                status=RetrievalStatus.NOT_FOUND,
                warnings=[],
                elapsed_ms=elapsed_ms,
            )

        # Check rerank cache first
        if self._cache is not None:
            candidate_ids = [c.chunk_id for c in request.candidates]
            cache_key = self._cache.make_key(request.original_query, candidate_ids)
            cached_candidates = self._cache.get(cache_key)
            if cached_candidates is not None:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.info(
                    "rerank_cache_hit query_len=%d candidates=%d rerank_ms=%.1f",
                    len(request.original_query),
                    len(cached_candidates),
                    elapsed_ms,
                )
                # Apply limit from request
                limited = cached_candidates[: request.limit]
                return self._result(
                    request,
                    candidates=limited,
                    status=RetrievalStatus.SUFFICIENT,
                    warnings=["Rerank cache hit."],
                    elapsed_ms=elapsed_ms,
                )

        if not self.circuit_breaker.allow_request():
            self._log_model_metadata()
            elapsed_ms = (time.perf_counter() - started) * 1000
            return self._result(
                request,
                candidates=self._rrf_fallback(request.candidates, request.limit),
                status=RetrievalStatus.PARTIAL,
                warnings=["Reranker circuit is open; returned RRF fallback."],
                elapsed_ms=elapsed_ms,
            )

        try:
            scores = await asyncio.wait_for(
                asyncio.to_thread(
                    self.reranker.rerank_batch,
                    request.original_query,
                    request.candidates,
                ),
                timeout=self.timeout_seconds,
            )
            scores = validate_rerank_output(scores, len(request.candidates))
        except TimeoutError:
            self.circuit_breaker.record_failure()
            warning = "Reranker timed out; returned RRF fallback."
        except Exception as exc:  # noqa: BLE001 - fallback is required for any model error
            self.circuit_breaker.record_failure()
            warning = (
                f"Reranker failed ({type(exc).__name__}); returned RRF fallback."
            )
        else:
            self.circuit_breaker.record_success()
            self._log_model_metadata()
            scored = [
                candidate.model_copy(update={"rerank_score": score})
                for candidate, score in zip(request.candidates, scores, strict=True)
            ]
            scored.sort(
                key=lambda candidate: (
                    -float(candidate.rerank_score),
                    -candidate.fusion_score,
                    candidate.chunk_id,
                )
            )
            # Cache the full scored list for future requests with same candidates
            if self._cache is not None:
                candidate_ids = [c.chunk_id for c in request.candidates]
                cache_key = self._cache.make_key(request.original_query, candidate_ids)
                self._cache.set(cache_key, scored)
            elapsed_ms = (time.perf_counter() - started) * 1000
            return self._result(
                request,
                candidates=scored[: request.limit],
                status=RetrievalStatus.SUFFICIENT,
                warnings=[],
                elapsed_ms=elapsed_ms,
            )

        elapsed_ms = (time.perf_counter() - started) * 1000
        self._log_model_metadata()
        return self._result(
            request,
            candidates=self._rrf_fallback(request.candidates, request.limit),
            status=RetrievalStatus.PARTIAL,
            warnings=[warning],
            elapsed_ms=elapsed_ms,
        )


def build_reranker_service(settings: RAGSettings) -> RerankerService:
    reranker = CrossEncoderReranker(
        model_name=settings.reranker_model_name,
        revision=settings.reranker_model_revision,
        device=settings.reranker_device,
        backend=settings.reranker_backend,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )
    return RerankerService(
        reranker,
        timeout_seconds=settings.reranker_timeout_seconds,
        circuit_failure_threshold=settings.reranker_circuit_failure_threshold,
        circuit_cooldown_seconds=settings.reranker_circuit_cooldown_seconds,
        cache_enabled=settings.cache_enabled,
    )
