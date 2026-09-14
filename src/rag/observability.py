"""Privacy-preserving metrics, logs and local tracing for governed RAG."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

try:  # Optional integrations: local fallback remains fully testable.
    import structlog
except ImportError:  # pragma: no cover - exercised when optional deps are absent
    structlog = None  # type: ignore[assignment]

try:
    from opentelemetry import trace as otel_trace
except ImportError:  # pragma: no cover
    otel_trace = None  # type: ignore[assignment]

try:
    from prometheus_client import Counter, Histogram
except ImportError:  # pragma: no cover
    Counter = Histogram = None  # type: ignore[assignment,misc]


METRIC_NAMES = (
    "query_transform_latency",
    "dense_latency",
    "sparse_latency",
    "fusion_latency",
    "rerank_latency",
    "context_expansion_latency",
    "total_retrieval_latency",
    "candidate_count",
    "final_context_count",
    "retry_count",
    "abstain_rate",
    "forbidden_rate",
    "fallback_rate",
    "retrieval_error_count",
    "reranker_error_count",
    "llm_error_count",
    "input_guardrail_latency",
    "retrieval_guardrail_latency",
    "output_guardrail_latency",
    "guardrail_block_rate",
    "guardrail_sanitize_rate",
)

_SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "api_key",
    "secret",
    "authorization",
    "content",
    "text",
    "document",
    "prompt",
}


def hash_identifier(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _safe_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    """Drop secrets and document-bearing values before structured logging."""

    safe: dict[str, Any] = {}
    for key, value in fields.items():
        lowered = key.lower()
        if lowered in {"query", "question", "raw_query"} or any(marker in lowered for marker in _SENSITIVE_KEYS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple, set)):
            safe[key] = [str(item) for item in value[:20]]
    return safe


@dataclass
class SpanRecord:
    name: str
    started_at: float
    duration_ms: float = 0.0
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"


@dataclass
class TraceRecord:
    trace_id: str
    fields: dict[str, str]
    started_at: float
    spans: list[SpanRecord] = field(default_factory=list)
    finished_at: float | None = None


class MetricsRegistry:
    """Prometheus-backed registry with an in-memory fallback for tests."""

    def __init__(self) -> None:
        self.values = {name: 0.0 for name in METRIC_NAMES}
        self._histograms: dict[str, Any] = {}
        self._counters: dict[str, Any] = {}
        if Histogram is not None and Counter is not None:
            for name in METRIC_NAMES:
                if name.endswith("latency") or name.endswith("count"):
                    self._histograms[name] = Histogram(f"rag_{name}", f"RAG {name}", registry=None)
                else:
                    self._counters[name] = Counter(f"rag_{name}", f"RAG {name}", registry=None)

    def observe(self, name: str, value: float) -> None:
        if name not in self.values:
            return
        value = float(value)
        self.values[name] = value
        metric = self._histograms.get(name)
        if metric is not None:
            metric.observe(value)

    def increment(self, name: str, value: float = 1.0) -> None:
        if name not in self.values:
            return
        self.values[name] += float(value)
        metric = self._counters.get(name)
        if metric is not None:
            metric.inc(value)

    def snapshot(self) -> dict[str, float]:
        return dict(self.values)


class RAGObservability:
    """One-process trace store; no SaaS exporter is configured by default."""

    def __init__(self, *, logger_name: str = "src.rag") -> None:
        self.metrics = MetricsRegistry()
        self.traces: dict[str, TraceRecord] = {}
        self.logger = structlog.get_logger(logger_name) if structlog is not None else logging.getLogger(logger_name)
        self.tracer = otel_trace.get_tracer("p234.rag") if otel_trace is not None else None

    def start_trace(
        self,
        *,
        trace_id: str | None,
        thread_id: str,
        tenant_id: str | None,
        user_id: str | None,
        query: str | None,
        index_version: str,
        embedding_model: str,
        reranker_model: str,
        policy_version: str,
    ) -> TraceRecord:
        trace = TraceRecord(
            trace_id=trace_id or str(uuid.uuid4()),
            fields={
                "trace_id": trace_id or "",
                "thread_id": thread_id,
                "tenant_id": tenant_id or "",
                "user_id_hash": hash_identifier(user_id),
                "query_hash": hash_identifier(query),
                "index_version": index_version,
                "embedding_model": embedding_model,
                "reranker_model": reranker_model,
                "policy_version": policy_version,
            },
            started_at=time.perf_counter(),
        )
        trace.fields["trace_id"] = trace.trace_id
        self.traces[trace.trace_id] = trace
        self.log("trace_started", **trace.fields)
        return trace

    @contextmanager
    def span(self, name: str, state: Mapping[str, Any]):
        trace_id = str(state.get("trace_id") or "")
        trace = self.traces.get(trace_id)
        started = time.perf_counter()
        record = SpanRecord(name=name, started_at=started)
        otel_span = None
        if self.tracer is not None:
            otel_span = self.tracer.start_span(name)
            otel_span.set_attribute("trace_id", trace_id)
            otel_span.set_attribute("thread_id", str(state.get("thread_id", "")))
        try:
            yield record
        except Exception:
            record.status = "error"
            raise
        finally:
            record.duration_ms = (time.perf_counter() - started) * 1000
            if trace is not None:
                record.attributes = _safe_fields(trace.fields)
                trace.spans.append(record)
            if otel_span is not None:
                otel_span.set_attribute("duration_ms", record.duration_ms)
                otel_span.end()
            self.log(
                "node_span",
                node=name,
                trace_id=trace_id,
                duration_ms=round(record.duration_ms, 3),
                status=record.status,
            )

    def finish_trace(self, state: Mapping[str, Any]) -> None:
        trace = self.traces.get(str(state.get("trace_id") or ""))
        if trace is None or trace.finished_at is not None:
            return
        trace.finished_at = time.perf_counter()
        self.metrics.observe(
            "total_retrieval_latency",
            (trace.finished_at - trace.started_at) * 1000,
        )
        self.log(
            "trace_finished",
            trace_id=trace.trace_id,
            duration_ms=round((trace.finished_at - trace.started_at) * 1000, 3),
            outcome=state.get("outcome", ""),
        )

    def log(self, event: str, **fields: Any) -> None:
        safe = _safe_fields(fields)
        if structlog is not None:
            self.logger.info(event, **safe)
        else:
            self.logger.info(json.dumps({"event": event, **safe}, sort_keys=True))

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        return self.traces.get(trace_id)


__all__ = [
    "METRIC_NAMES",
    "MetricsRegistry",
    "RAGObservability",
    "SpanRecord",
    "TraceRecord",
    "hash_identifier",
]
