from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import date
from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.domain.schemas import (
    Candidate,
    ContextWindow,
    EvidenceAction,
    EvidenceAssessment,
    GeneratedAnswer,
    Latency,
    RerankResult,
    RetrievalResult,
    RetrievalStatus,
    RetrievedChunk,
    UserContext,
)
from src.rag.answer_grounding import verify_answer_grounding
from src.rag.chitchat import (
    chitchat_response_node,
    resolve_chitchat_templates,
    resolve_tenant_display_name,
)
from src.rag.citation_validator import (
    MIN_CITATIONS_FOR_SUFFICIENT,
    validate_and_build_citations,
)
from src.rag.config import RAGSettings
from src.rag.decompose import decompose_query_node
from src.rag.generator import AnswerGenerator
from src.rag.intent_router import QueryIntent, classify_intent
from src.rag.observability import RAGObservability, hash_identifier
from src.rag.persistence import (
    CheckpointRetentionPolicy,
    GovernedInMemorySaver,
    query_digest,
)
from src.retrieval.context_expansion import ContextChunkProvider, build_context_window
from src.retrieval.evidence_gate import evaluate_evidence
from src.retrieval.evidence_rerank import rerank_evidence
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.hyde import generate_hyde_passage
from src.retrieval.query_expansion import build_lexical_query, expand_query
from src.retrieval.query_transform import build_query_variants
from src.retrieval.retrieval_cache import RetrievalCache, get_retrieval_cache
from src.security.policy import build_access_filter


class RetrievalState(TypedDict, total=False):
    """State contract for the non-bypassable retrieval workflow."""

    original_query: str
    query: str
    rerank_query: str
    conversation_context: str
    hyde_passage: str
    user: UserContext
    as_of_date: date | None
    request_id: str
    index_version: str
    query_hash: str
    trace_id: str
    thread_id: str
    tenant_id: str
    user_id_hash: str
    embedding_model: str
    reranker_model: str
    policy_version: str
    candidate_ids: list[str]
    candidate_scores: dict[str, float]
    settings: RAGSettings
    retriever: Any
    reranker_service: Any
    generator: Any
    context_provider: Any
    attempts: int
    max_attempts: int
    transformed_queries: list[str]
    policy: Any
    retrieval_result: RetrievalResult
    rerank_result: RerankResult
    final_contexts: list[Candidate]
    context_window: ContextWindow | None
    evidence_assessment: EvidenceAssessment
    evidence_status: RetrievalStatus
    evidence_decision: EvidenceAction
    evidence_reason: str
    generated_answer: GeneratedAnswer
    answer: str
    citations: list[Any]
    cited_chunk_ids: list[str]
    warnings: list[str]
    confidence: str
    error_code: str
    error_message: str
    escalation_required: bool
    outcome: str
    human_decision: str
    human_audit: list[dict[str, str]]
    retry_requested: bool
    human_in_loop: bool
    visited: list[str]
    intent: QueryIntent | None
    # Resolved chitchat templates (injected at workflow startup with the
    # configured tenant name) — keep this here so langgraph's TypedDict
    # state filter does not strip the field before the chitchat node runs.
    chitchat_templates: dict[str, str]
    # Resolved tenant display name for the current user. Injected at
    # workflow startup so the LLM generator can use the same per-user
    # branding as the chitchat node without re-resolving it.
    tenant_display_name: str


RetrieveFn = Callable[
    [str, UserContext, date | None],
    Awaitable[Any],
]  # may accept embed_text=... kwarg for HyDE
RerankFn = Callable[[str, Sequence[Candidate], RAGSettings], Awaitable[RerankResult]]
ExpandFn = Callable[[Sequence[Candidate], RetrievalState], Awaitable[Any]]


def _visit(state: RetrievalState, node: str) -> list[str]:
    return [*state.get("visited", []), node]


def _settings(state: RetrievalState, fallback: RAGSettings) -> RAGSettings:
    value = state.get("settings")
    return value if isinstance(value, RAGSettings) else fallback


def _candidate_from_retrieved(item: RetrievedChunk) -> Candidate:
    metadata = dict(item.metadata)
    return Candidate(
        chunk_id=item.chunk_id,
        document_id=str(metadata.get("document_id") or item.chunk_id),
        version_id=str(metadata.get("version_id") or item.chunk_id),
        content=item.text,
        metadata=metadata,
        fusion_score=max(float(item.score), 0.0),
        rerank_score=float(item.score),
    )


def _as_candidates(items: Any) -> list[Candidate]:
    if isinstance(items, RetrievalResult):
        return list(items.candidates)
    candidates: list[Candidate] = []
    for item in items or []:
        if isinstance(item, Candidate):
            candidates.append(item)
        elif isinstance(item, RetrievedChunk):
            candidates.append(_candidate_from_retrieved(item))
        else:
            raise TypeError(f"Unsupported retrieval item: {type(item).__name__}")
    return candidates


def _retrieval_result(
    output: Any,
    *,
    query: str,
    index_version: str,
    elapsed_ms: float,
) -> RetrievalResult:
    if isinstance(output, RetrievalResult):
        return output
    candidates = _as_candidates(output)
    return RetrievalResult(
        status=RetrievalStatus.SUFFICIENT if candidates else RetrievalStatus.NOT_FOUND,
        original_query=query,
        transformed_queries=[],
        candidates=candidates,
        latency=Latency(total_ms=elapsed_ms),
        index_version=index_version,
    )


def _retrieved_chunks(candidates: Sequence[Candidate]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=item.chunk_id,
            text=item.content,
            score=float(item.rerank_score if item.rerank_score is not None else item.fusion_score),
            source="workflow",
            metadata={
                **item.metadata,
                "document_id": item.document_id,
                "version_id": item.version_id,
                # Forward rerank_score so citation_validator can extract it
                "rerank_score": item.rerank_score,
            },
        )
        for item in candidates
    ]


def _candidate_from_segment(segment: Any) -> Candidate:
    metadata = dict(segment.metadata)
    # Extract rerank_score from segment metadata so it flows through to citations
    rerank_score_raw = metadata.get("rerank_score")
    rerank_score = (
        float(rerank_score_raw)
        if rerank_score_raw is not None and isinstance(rerank_score_raw, (int, float))
        else None
    )
    return Candidate(
        chunk_id=segment.chunk_id,
        document_id=segment.document_id,
        version_id=segment.version_id,
        content=segment.content,
        metadata=metadata,
        fusion_score=0.0,
        rerank_score=rerank_score,
    )


def _forbidden_result(query: str, index_version: str) -> RetrievalResult:
    return RetrievalResult(
        status=RetrievalStatus.FORBIDDEN,
        original_query=query,
        candidates=[],
        latency=Latency(total_ms=0.0),
        index_version=index_version,
    )


class RetrievalWorkflow:
    """Compiled graph whose topology makes retrieval governance mandatory."""

    def __init__(
        self,
        settings: RAGSettings,
        retriever: HybridRetriever | None = None,
        reranker_service: Any | None = None,
        generator: AnswerGenerator | None = None,
        context_provider: ContextChunkProvider | None = None,
        *,
        retrieve_fn: RetrieveFn | None = None,
        rerank_fn: RerankFn | None = None,
        expand_fn: ExpandFn | None = None,
        checkpointer: BaseCheckpointSaver | None = None,
        retention_policy: CheckpointRetentionPolicy | None = None,
        observability: RAGObservability | None = None,
        hyde_llm: Any | None = None,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.reranker_service = reranker_service
        self.generator = generator
        self.context_provider = context_provider
        self.retrieve_fn = retrieve_fn
        self.rerank_fn = rerank_fn
        self.expand_fn = expand_fn
        self.checkpointer = checkpointer or GovernedInMemorySaver()
        self.retention_policy = retention_policy or CheckpointRetentionPolicy()
        self._runtime_inputs: dict[str, RetrievalState] = {}
        self.observability = observability or RAGObservability()
        self.hyde_llm = hyde_llm
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(RetrievalState)
        nodes = {
            "build_user_context_node": self.build_user_context_node,
            "classify_intent_node": self.classify_intent_node,
            "chitchat_response_node": self._chitchat_node,
            "decompose_query_node": self._decompose_node,
            "build_policy_node": self.build_policy_node,
            "transform_query_node": self.transform_query_node,
            "hybrid_retrieve_node": self.hybrid_retrieve_node,
            "rerank_node": self.rerank_node,
            "expand_context_node": self.expand_context_node,
            "evidence_gate_node": self.evidence_gate_node,
            "rewrite_query_node": self.rewrite_query_node,
            "generate_answer_node": self.generate_answer_node,
            "validate_citation_node": self.validate_citation_node,
            "abstain_node": self.abstain_node,
        }
        for name, node in nodes.items():
            graph.add_node(name, self._instrument_node(name, node))

        graph.add_edge(START, "build_user_context_node")
        graph.add_edge("build_user_context_node", "classify_intent_node")
        graph.add_conditional_edges(
            "classify_intent_node",
            self._route_after_intent,
            {
                "chitchat_response_node": "chitchat_response_node",
                "decompose_query_node": "decompose_query_node",
                "abstain_node": "abstain_node",
                "build_policy_node": "build_policy_node",
            },
        )
        graph.add_edge("chitchat_response_node", END)
        graph.add_edge("decompose_query_node", "build_policy_node")
        graph.add_edge("build_policy_node", "transform_query_node")
        graph.add_edge("transform_query_node", "hybrid_retrieve_node")
        graph.add_edge("hybrid_retrieve_node", "rerank_node")
        graph.add_edge("rerank_node", "expand_context_node")
        graph.add_edge("expand_context_node", "evidence_gate_node")
        graph.add_conditional_edges(
            "evidence_gate_node",
            self._route_evidence,
            {
                "generate_answer_node": "generate_answer_node",
                "rewrite_query_node": "rewrite_query_node",
                "abstain_node": "abstain_node",
            },
        )
        graph.add_edge("rewrite_query_node", "transform_query_node")
        graph.add_edge("generate_answer_node", "validate_citation_node")
        graph.add_edge("validate_citation_node", END)
        graph.add_conditional_edges(
            "abstain_node",
            self._route_after_abstain,
            {"retry": "transform_query_node", "end": END},
        )
        return graph.compile(checkpointer=self.checkpointer)

    def _chitchat_node(self, state: RetrievalState) -> dict:
        return chitchat_response_node(state)

    def _decompose_node(self, state: RetrievalState) -> dict:
        return decompose_query_node(state, subgraph=self)

    def _instrument_node(self, name: str, node: Callable[[RetrievalState], Any]):
        async def wrapped(state: RetrievalState) -> dict:
            with self.observability.span(name, state):
                started = time.perf_counter()
                result = await node(state)
                elapsed_ms = (time.perf_counter() - started) * 1000
                self._observe_node_metrics(name, state, result, elapsed_ms)
                return result

        return wrapped

    def _observe_node_metrics(
        self,
        name: str,
        state: RetrievalState,
        result: Mapping[str, Any],
        elapsed_ms: float,
    ) -> None:
        metric_by_node = {
            "transform_query_node": "query_transform_latency",
            "expand_context_node": "context_expansion_latency",
        }
        if name in metric_by_node:
            self.observability.metrics.observe(metric_by_node[name], elapsed_ms)
        retrieval = result.get("retrieval_result")
        if retrieval is not None:
            latency = retrieval.latency
            self.observability.metrics.observe("dense_latency", latency.dense_ms)
            self.observability.metrics.observe("sparse_latency", latency.sparse_ms)
            self.observability.metrics.observe("fusion_latency", latency.fusion_ms)
            self.observability.metrics.observe("candidate_count", len(retrieval.candidates))
            if retrieval.status is RetrievalStatus.FORBIDDEN:
                self.observability.metrics.increment("forbidden_rate")
        reranked = result.get("rerank_result")
        if reranked is not None:
            self.observability.metrics.observe("rerank_latency", reranked.latency.rerank_ms or elapsed_ms)
        if "final_contexts" in result:
            self.observability.metrics.observe("final_context_count", len(result.get("final_contexts") or []))
        if name == "rewrite_query_node":
            self.observability.metrics.increment("retry_count")
        if name == "abstain_node":
            self.observability.metrics.increment("abstain_rate")
        if result.get("error_code"):
            self.observability.metrics.increment("fallback_rate")
            code = str(result["error_code"])
            if code.startswith("RETRIEVAL"):
                self.observability.metrics.increment("retrieval_error_count")
            elif code.startswith("RERANK"):
                self.observability.metrics.increment("reranker_error_count")
            elif code.startswith(("GENERATOR", "CITATION")):
                self.observability.metrics.increment("llm_error_count")

    @staticmethod
    def _config(thread_id: str) -> dict[str, dict[str, str]]:
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id is required for checkpointed workflow calls.")
        return {"configurable": {"thread_id": thread_id.strip()}}

    @staticmethod
    def _thread_id(config: Any) -> str:
        try:
            thread_id = config["configurable"]["thread_id"]
        except (KeyError, TypeError):
            raise ValueError("thread_id is required for checkpointed workflow calls.") from None
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("thread_id is required for checkpointed workflow calls.")
        return thread_id.strip()

    async def build_user_context_node(self, state: RetrievalState) -> dict:
        user = state.get("user")
        if not isinstance(user, UserContext):
            return {
                "error_code": "AUTH_CONTEXT_MISSING",
                "error_message": "Authenticated UserContext is required.",
                "visited": _visit(state, "build_user_context_node"),
            }
        return {
            "user": user,
            "original_query": state.get("original_query") or state.get("query", ""),
            "query": state.get("query") or state.get("original_query", ""),
            "query_hash": query_digest(state.get("original_query") or state.get("query", "")),
            "attempts": state.get("attempts", 0),
            "max_attempts": min(state.get("max_attempts", 2), 2),
            "visited": _visit(state, "build_user_context_node"),
        }

    async def classify_intent_node(self, state: RetrievalState) -> dict:
        """Decide whether to short-circuit small-talk or run the full pipeline."""

        original = (state.get("original_query") or state.get("query") or "").strip()
        try:
            intent = classify_intent(original) if original else QueryIntent.SEMANTIC
        except (TypeError, ValueError):
            intent = QueryIntent.SEMANTIC
        return {
            "intent": intent,
            "visited": _visit(state, "classify_intent_node"),
        }

    def _route_after_intent(self, state: RetrievalState) -> str:
        intent = state.get("intent")

        # Short-circuit: out-of-scope queries don't get answered
        if intent in (QueryIntent.OUT_OF_SCOPE,):
            return "abstain_node"

        # Short-circuit: small talk doesn't need retrieval
        if intent in {
            QueryIntent.SMALL_TALK,
            QueryIntent.SELF_INTRODUCTION,
            QueryIntent.HELP,
        }:
            return "chitchat_response_node"

        # Multi-intent queries need decomposition first
        if intent is QueryIntent.MULTI_INTENT:
            return "decompose_query_node"

        # Ambiguous queries: flag for clarification, but still try retrieval
        # if the user has prior context (follow-up handling)
        if intent is QueryIntent.AMBIGUOUS:
            # Check if there's conversation history indicating context
            # For now, treat as abstention requiring clarification
            return "abstain_node"

        # All other intents (IDENTIFIER, KEYWORD, SEMANTIC, MIXED,
        # INFORMATION_POLICY, PROCEDURE, COMPARISON, CONDITION_LOOKUP,
        # FORM_GENERATION, FORM_INFO, FOLLOW_UP) go through full pipeline
        return "build_policy_node"

    async def build_policy_node(self, state: RetrievalState) -> dict:
        user = state.get("user")
        if not isinstance(user, UserContext):
            return {"policy": None, "visited": _visit(state, "build_policy_node")}
        return {
            "policy": build_access_filter(user, as_of=state.get("as_of_date")),
            "visited": _visit(state, "build_policy_node"),
        }

    async def transform_query_node(self, state: RetrievalState) -> dict:
        query = state.get("query") or state.get("original_query", "")
        try:
            variants = build_query_variants(query)
        except (TypeError, ValueError) as exc:
            return {
                "error_code": "INVALID_QUERY",
                "error_message": str(exc),
                "visited": _visit(state, "transform_query_node"),
            }
        # Append lexical expansion variants (deterministic, no LLM cost).
        # Each variant is a candidate query; the hybrid retriever fuses
        # results across all of them via RRF.
        if self.settings.query_expansion_enabled:
            extras = expand_query(query, max_extra=self.settings.query_expansion_max_extra)
            for variant in extras:
                if variant not in variants:
                    variants.append(variant)
        # HyDE: generate a hypothetical passage so dense retrieval can
        # embed the passage instead of the raw query. Best-effort — if
        # the generator is missing or slow, we silently fall back to
        # the original query.
        hyde_passage: str = ""
        if self.settings.hyde_enabled and self.hyde_llm is not None:
            passage = await generate_hyde_passage(
                query,
                self.hyde_llm,
                timeout=self.settings.hyde_timeout_seconds,
            )
            if passage:
                hyde_passage = passage
                marker = f"[HyDE] {passage}"
                if marker not in variants:
                    variants.append(marker)
        return {
            "query": variants[0],
            # Rerank with the same bounded domain vocabulary used by the
            # lexical retrieval legs. Numeric-answer gating and local-window
            # scoring still prevent generic headings from beating answer rows.
            "rerank_query": (
                build_lexical_query(
                    query,
                    max_extra=self.settings.query_expansion_max_extra,
                )
                if self.settings.query_expansion_enabled
                else query
            ),
            "hyde_passage": hyde_passage,
            "transformed_queries": variants,
            "visited": _visit(state, "transform_query_node"),
        }

    async def hybrid_retrieve_node(self, state: RetrievalState) -> dict:
        visited = _visit(state, "hybrid_retrieve_node")
        user = state.get("user")
        settings = _settings(state, self.settings)
        attempts = state.get("attempts", 0) + 1
        index_version = str(state.get("index_version") or settings.qdrant_collection)
        if not isinstance(user, UserContext):
            return {
                "attempts": attempts,
                "index_version": index_version,
                "retrieval_result": _forbidden_result(state.get("query", ""), index_version),
                "visited": visited,
            }
        retriever = self.retrieve_fn
        if retriever is None:
            configured_retriever = self.retriever or state.get("retriever")
            if configured_retriever is None:
                return {
                    "attempts": attempts,
                    "index_version": index_version,
                    "error_code": "RETRIEVER_MISSING",
                    "retrieval_result": _forbidden_result(state.get("query", ""), index_version),
                    "visited": visited,
                }
            retriever = configured_retriever.search
        started = time.perf_counter()
        # HyDE: the hypothetical passage is embedded for dense retrieval so the
        # vocabulary in the passage (answer-like) matches the chunk space better.
        # Identifier filtering and sparse retrieval still use the original query.
        hyde_passage = state.get("hyde_passage")

        # Cache check: skip retrieval if the same query was processed recently
        # by the same tenant. Bypass when as_of_date is set (policy versioning
        # may differ across dates) or when HyDE is enabled (passage changes
        # the embedding space).
        cache: RetrievalCache | None = None
        if (
            settings.cache_enabled
            and state.get("as_of_date") is None
            and not hyde_passage
            and not state.get("bypass_cache")
        ):
            cache = get_retrieval_cache()
            cache_key = RetrievalCache.make_key(
                state["query"],
                user.tenant_id,
                user.department,
                settings.fused_limit,
            )
            cached = cache.get(cache_key)
            if cached is not None:
                self.observability.metrics.increment("retrieval_cache_hit")
                return {
                    "attempts": attempts,
                    "index_version": cached.index_version,
                    "error_code": "",
                    "error_message": "",
                    "retrieval_result": cached.model_copy(update={"transformed_queries": state.get("transformed_queries", [])}),
                    "visited": visited,
                }
            self.observability.metrics.increment("retrieval_cache_miss")

        try:
            output = retriever(
                state["query"],  # original, for identifier filter + sparse
                user,
                state.get("as_of_date"),
                embed_text=hyde_passage,  # embed this instead if HyDE was applied
            )
            if inspect.isawaitable(output):
                output = await asyncio.wait_for(
                    output,
                    timeout=settings.retrieval_timeout_seconds,
                )
            result = _retrieval_result(
                output,
                query=state["query"],
                index_version=index_version,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        except TimeoutError:
            return {
                "attempts": attempts,
                "index_version": index_version,
                "error_code": "RETRIEVAL_TIMEOUT",
                "retrieval_result": RetrievalResult(
                    status=RetrievalStatus.NOT_FOUND,
                    original_query=state["query"],
                    candidates=[],
                    warnings=["Hybrid retrieval timed out."],
                    latency=Latency(total_ms=(time.perf_counter() - started) * 1000),
                    index_version=index_version,
                ),
                "visited": visited,
            }
        except Exception as exc:  # noqa: BLE001 - graph boundary maps backend errors
            import logging
            import traceback
            logging.getLogger("rag.retrieve").error(
                "Hybrid retrieval raised %s: %s\n%s",
                type(exc).__name__, exc, traceback.format_exc(),
            )
            return {
                "attempts": attempts,
                "index_version": index_version,
                "error_code": "RETRIEVAL_FAILED",
                "error_message": type(exc).__name__,
                "retrieval_result": RetrievalResult(
                    status=RetrievalStatus.NOT_FOUND,
                    original_query=state["query"],
                    candidates=[],
                    warnings=[f"Hybrid retrieval failed ({type(exc).__name__})."],
                    latency=Latency(total_ms=(time.perf_counter() - started) * 1000),
                    index_version=index_version,
                ),
                "visited": visited,
            }
        # Populate cache after a successful retrieval so the next query with
        # the same text + tenant hits the cache and skips Qdrant.
        if cache is not None and result.candidates:
            cache.set(cache_key, result, ttl=settings.cache_ttl_seconds)

        return {
            "attempts": attempts,
            "index_version": result.index_version,
            "error_code": "",
            "error_message": "",
            "retrieval_result": result.model_copy(update={"transformed_queries": state.get("transformed_queries", [])}),
            "visited": visited,
        }

    async def rerank_node(self, state: RetrievalState) -> dict:
        visited = _visit(state, "rerank_node")
        retrieval = state.get("retrieval_result")
        if not isinstance(retrieval, RetrievalResult):
            return {"error_code": "RETRIEVAL_RESULT_MISSING", "visited": visited}
        if retrieval.status is RetrievalStatus.FORBIDDEN:
            result = RerankResult(
                status=RetrievalStatus.FORBIDDEN,
                original_query=state["query"],
                candidates=[],
                latency=Latency(total_ms=0.0),
            )
            return {"rerank_result": result, "visited": visited}
        if not retrieval.candidates:
            result = RerankResult(
                status=RetrievalStatus.NOT_FOUND,
                original_query=state["query"],
                candidates=[],
                latency=Latency(total_ms=0.0),
            )
            return {"rerank_result": result, "visited": visited}

        settings = _settings(state, self.settings)
        rerank_query = state.get("rerank_query") or state["query"]
        try:
            if self.rerank_fn is not None:
                result = await asyncio.wait_for(
                    self.rerank_fn(rerank_query, retrieval.candidates, settings),
                    timeout=settings.rerank_timeout_seconds,
                )
            elif self.reranker_service is not None or state.get("reranker_service") is not None:
                result = await asyncio.wait_for(
                    rerank_evidence(
                        original_query=rerank_query,
                        candidates=retrieval.candidates,
                        reranker_service=self.reranker_service or state["reranker_service"],
                        settings=settings,
                    ),
                    timeout=settings.rerank_timeout_seconds,
                )
            else:
                raise RuntimeError("reranker service is not configured")
        except TimeoutError:
            return {
                "error_code": "RERANK_TIMEOUT",
                "error_message": "Reranker exceeded hard latency budget.",
                "rerank_result": RerankResult(
                    status=RetrievalStatus.CONFLICT,
                    original_query=state["query"],
                    candidates=[],
                    warnings=["Reranker timed out."],
                    latency=Latency(total_ms=0.0),
                ),
                "visited": visited,
            }
        except Exception as exc:  # noqa: BLE001 - never bypass reranker on failure
            return {
                "error_code": "RERANK_FAILED",
                "error_message": type(exc).__name__,
                "rerank_result": RerankResult(
                    status=RetrievalStatus.CONFLICT,
                    original_query=state["query"],
                    candidates=[],
                    warnings=[f"Reranker failed ({type(exc).__name__})."],
                    latency=Latency(total_ms=0.0),
                ),
                "visited": visited,
            }
        return {
            "rerank_result": result,
            "error_code": "",
            "error_message": "",
            "visited": visited,
        }

    async def expand_context_node(self, state: RetrievalState) -> dict:
        visited = _visit(state, "expand_context_node")
        reranked = state.get("rerank_result")
        if not isinstance(reranked, RerankResult):
            return {"final_contexts": [], "visited": visited}
        winning = list(reranked.candidates)
        if not winning:
            return {"final_contexts": [], "context_window": None, "visited": visited}
        try:
            if self.expand_fn is not None:
                expanded = await self.expand_fn(winning, state)
                if isinstance(expanded, ContextWindow):
                    contexts = [_candidate_from_segment(segment) for segment in expanded.segments]
                    return {
                        "final_contexts": contexts,
                        "context_window": expanded,
                        "visited": visited,
                    }
                return {"final_contexts": _as_candidates(expanded), "visited": visited}
            context_provider = self.context_provider or state.get("context_provider")
            if context_provider is not None and isinstance(state.get("user"), UserContext):
                window = build_context_window(
                    winning,
                    provider=context_provider,
                    user=state["user"],
                    token_budget=_settings(state, self.settings).context_token_budget,
                    as_of=state.get("as_of_date"),
                )
                contexts = [_candidate_from_segment(segment) for segment in window.segments]
                return {"final_contexts": contexts, "context_window": window, "visited": visited}
        except Exception as exc:  # noqa: BLE001 - context expansion is governed
            return {
                "error_code": "CONTEXT_EXPANSION_FAILED",
                "error_message": type(exc).__name__,
                "final_contexts": [],
                "visited": visited,
            }
        return {"final_contexts": winning, "visited": visited}

    async def evidence_gate_node(self, state: RetrievalState) -> dict:
        visited = _visit(state, "evidence_gate_node")
        reranked = state.get("rerank_result")
        if not isinstance(reranked, RerankResult):
            return {
                "evidence_status": RetrievalStatus.NOT_FOUND,
                "evidence_decision": EvidenceAction.ABSTAIN,
                "evidence_reason": "Rerank result is missing.",
                "visited": visited,
            }
        assessment = evaluate_evidence(
            reranked,
            _settings(state, self.settings),
            retry_count=max(state.get("attempts", 1) - 1, 0),
        )
        return {
            "evidence_assessment": assessment,
            "evidence_status": assessment.status,
            "evidence_decision": assessment.decision,
            "evidence_reason": assessment.reason,
            "visited": visited,
        }

    def _route_evidence(self, state: RetrievalState) -> str:
        decision = state.get("evidence_decision")
        if isinstance(decision, str):
            try:
                decision = EvidenceAction(decision)
            except ValueError:
                pass
        if state.get("error_code"):
            return "abstain_node"
        if decision is EvidenceAction.GENERATE:
            return "generate_answer_node"

        # Bail early when the top rerank score is near-zero — retrying the
        # query rewrite will not recover candidates that were never retrieved.
        # The rewrite appends "căn cứ văn bản hiện hành" which is ineffective
        # when the dense/sparse legs returned no relevant chunks.
        # Use the configurable minimum_evidence_score instead of hard-coded 0.10.
        reranked = state.get("rerank_result")
        settings = _settings(state, self.settings)
        if isinstance(reranked, RerankResult) and reranked.candidates:
            top_score = reranked.candidates[0].rerank_score
            min_threshold = settings.minimum_evidence_score
            if top_score is not None and top_score < min_threshold:
                return "abstain_node"

        if decision is EvidenceAction.RETRY and state.get("attempts", 0) < min(
            state.get("max_attempts", 2), 2
        ):
            return "rewrite_query_node"
        return "abstain_node"

    def _route_after_abstain(self, state: RetrievalState) -> str:
        if state.get("retry_requested") and state.get("attempts", 0) < min(state.get("max_attempts", 2), 2):
            return "retry"
        return "end"

    async def rewrite_query_node(self, state: RetrievalState) -> dict:
        original = state.get("original_query") or state.get("query", "")
        rewritten = f"{original} căn cứ văn bản hiện hành"
        return {
            "query": rewritten,
            "original_query": original,
            "visited": _visit(state, "rewrite_query_node"),
        }

    async def generate_answer_node(self, state: RetrievalState) -> dict:
        contexts = _retrieved_chunks(state.get("final_contexts", []))
        generator = self.generator or state.get("generator")
        if generator is None:
            return {
                "error_code": "GENERATOR_MISSING",
                "generated_answer": GeneratedAnswer(
                    answer="Tôi chưa có đủ căn cứ để kết luận.",
                    warnings=["Answer generator is not configured."],
                    confidence="low",
                ),
                "visited": _visit(state, "generate_answer_node"),
            }
        settings = _settings(state, self.settings)
        try:
            generation_query = state.get("original_query", state["query"])
            conversation_context = str(
                state.get("conversation_context") or ""
            ).strip()
            if conversation_context:
                generation_query = (
                    f"CURRENT QUESTION:\n{generation_query}\n\n"
                    "CONVERSATION CONTEXT (for reference resolution only; "
                    "not factual evidence):\n"
                    f"{conversation_context}"
                )
            generated = await asyncio.wait_for(
                generator.generate(
                    generation_query,
                    contexts,
                    tenant_display_name=state.get("tenant_display_name"),
                ),
                timeout=settings.generation_timeout_seconds,
            )
        except TimeoutError:
            generated = GeneratedAnswer(
                answer="Tôi chưa có đủ căn cứ để kết luận.",
                warnings=["Answer generation timed out."],
                confidence="low",
            )
        except Exception as exc:  # noqa: BLE001 - generation is still citation-validated
            generated = GeneratedAnswer(
                answer="Tôi chưa có đủ căn cứ để kết luận.",
                warnings=[f"Answer generation failed ({type(exc).__name__})."],
                confidence="low",
            )
        return {
            "generated_answer": generated,
            "answer": generated.answer,
            "cited_chunk_ids": generated.cited_chunk_ids,
            "warnings": generated.warnings,
            "confidence": generated.confidence,
            "visited": _visit(state, "generate_answer_node"),
        }

    async def validate_citation_node(self, state: RetrievalState) -> dict:
        generated = state.get("generated_answer") or GeneratedAnswer(
            answer=state.get("answer", ""),
            cited_chunk_ids=state.get("cited_chunk_ids", []),
            warnings=state.get("warnings", []),
            confidence=state.get("confidence", "low"),
        )
        evidence_status = state.get("evidence_status")
        if isinstance(evidence_status, str):
            try:
                evidence_status = RetrievalStatus(evidence_status)
            except ValueError:
                evidence_status = None
        # Stricter contract: SUFFICIENT evidence must produce >=2 unique
        # citations; PARTIAL still rides on a single citation. The
        # validator already enforces 1 minimum for any generation.
        expected_min = (
            MIN_CITATIONS_FOR_SUFFICIENT
            if evidence_status is RetrievalStatus.SUFFICIENT
            else 1
        )
        validated, citations = validate_and_build_citations(
            generated,
            _retrieved_chunks(state.get("final_contexts", [])),
            user=state.get("user"),
            as_of=state.get("as_of_date"),
            expected_min_citations=expected_min,
            focus_text=(
                f"{state.get('original_query', state.get('query', ''))}\n"
                f"{generated.answer}"
            ),
        )
        grounding = verify_answer_grounding(
            validated.answer,
            citations,
            question=state.get("original_query", state.get("query", "")),
            contexts=state.get("final_contexts", []),
        )
        outcome = "generated" if citations else "unverified"
        if citations and not grounding.supported:
            validated = validated.model_copy(
                update={
                    "answer": (
                        "Tôi chưa thể xác minh chắc chắn các chi tiết định lượng "
                        "trong câu trả lời từ phần nguồn đã trích dẫn."
                    ),
                    "warnings": [
                        *validated.warnings,
                        "Post-generation grounding check failed: "
                        + ", ".join(grounding.unsupported_claims),
                    ],
                    "confidence": "low",
                }
            )
            outcome = "unverified"
        return {
            "answer": validated.answer,
            "citations": citations,
            "warnings": validated.warnings,
            "confidence": validated.confidence,
            "outcome": outcome,
            "visited": _visit(state, "validate_citation_node"),
        }

    async def abstain_node(self, state: RetrievalState) -> dict:
        intent = state.get("intent")

        # Special handling for OUT_OF_SCOPE queries
        if intent is QueryIntent.OUT_OF_SCOPE:
            return {
                "answer": (
                    "Xin lỗi, câu hỏi của bạn nằm ngoài phạm vi hệ thống. "
                    "Tôi chỉ có thể hỗ trợ về quy định, chính sách và quy trình "
                    "của trường đại học."
                ),
                "citations": [],
                "warnings": [],
                "confidence": "low",
                "outcome": "out_of_scope",
                "escalation_required": False,
                "retry_requested": False,
                "visited": _visit(state, "abstain_node"),
            }

        # Special handling for AMBIGUOUS queries
        if intent is QueryIntent.AMBIGUOUS:
            return {
                "answer": (
                    "Tôi chưa hiểu rõ câu hỏi của bạn. Bạn có thể diễn đạt lại "
                    "hoặc cung cấp thêm ngữ cảnh để tôi hỗ trợ chính xác hơn?"
                ),
                "citations": [],
                "warnings": ["Câu hỏi không rõ ràng, yêu cầu người dùng làm rõ."],
                "confidence": "low",
                "outcome": "ambiguous",
                "escalation_required": False,
                "retry_requested": False,
                "visited": _visit(state, "abstain_node"),
            }

        status = state.get("evidence_status")
        if isinstance(status, str):
            try:
                status = RetrievalStatus(status)
            except ValueError:
                pass
        escalation = status is RetrievalStatus.CONFLICT
        reason = (
            state.get("evidence_reason")
            or state.get("error_message")
            or state.get("error_code", "Evidence is insufficient.")
        )
        if escalation and state.get("human_in_loop", False):
            candidate_ids = [item.chunk_id for item in state.get("final_contexts", []) or []]
            payload = {
                "kind": "evidence_conflict",
                "query_hash": state.get("query_hash")
                or query_digest(state.get("original_query") or state.get("query")),
                "candidate_ids": candidate_ids,
                "evidence_decision": str(
                    getattr(
                        state.get("evidence_decision"),
                        "value",
                        state.get("evidence_decision"),
                    )
                    or "abstain"
                ),
            }
            decision = interrupt(payload)
            if not isinstance(decision, dict):
                decision = {"decision": str(decision)}
            action = str(decision.get("decision", "reject")).lower()
            audit = {
                "decision": action,
                "actor_id": str(decision.get("actor_id", "unknown")),
                "submitted_at": str(decision.get("submitted_at", "")),
            }
            if action == "retry":
                return {
                    "human_decision": action,
                    "human_audit": [*state.get("human_audit", []), audit],
                    "retry_requested": True,
                    "error_code": "",
                    "error_message": "",
                    "outcome": "retrying",
                    "visited": _visit(state, "abstain_node"),
                }
            return {
                "answer": "Tôi chưa có đủ căn cứ để kết luận.",
                "citations": [],
                "warnings": [reason],
                "confidence": "low",
                "human_decision": action,
                "human_audit": [*state.get("human_audit", []), audit],
                "outcome": "human_approved" if action == "approve" else "human_rejected",
                "escalation_required": action != "approve",
                "retry_requested": False,
                "visited": _visit(state, "abstain_node"),
            }
        return {
            "answer": "Tôi chưa có đủ căn cứ để kết luận.",
            "citations": [],
            "warnings": [reason],
            "confidence": "low",
            "outcome": "human_escalation" if escalation else "abstained",
            "escalation_required": escalation,
            "retry_requested": False,
            "visited": _visit(state, "abstain_node"),
        }

    async def ainvoke(
        self,
        state: RetrievalState,
        config: dict[str, Any] | None = None,
        *,
        thread_id: str | None = None,
    ) -> RetrievalState:
        legacy_compat = config is None and thread_id is None
        if config is None:
            config = self._config(thread_id or f"legacy-{uuid.uuid4()}")
        current_thread = self._thread_id(config)
        runtime_state = dict(state)
        runtime_state["human_in_loop"] = not legacy_compat
        user = runtime_state.get("user")
        configured = config.get("configurable", {})
        query = runtime_state.get("original_query") or runtime_state.get("query", "")
        trace = self.observability.start_trace(
            trace_id=configured.get("trace_id"),
            thread_id=current_thread,
            tenant_id=getattr(user, "tenant_id", None),
            user_id=getattr(user, "user_id", None),
            query=query,
            index_version=str(runtime_state.get("index_version") or self.settings.qdrant_collection),
            embedding_model=self.settings.embedding_model,
            reranker_model=self.settings.reranker_model_name,
            policy_version="security.policy.v1",
        )
        runtime_state.update(
            {
                "trace_id": trace.trace_id,
                "thread_id": current_thread,
                "tenant_id": str(getattr(user, "tenant_id", "")),
                "user_id_hash": hash_identifier(getattr(user, "user_id", None)),
                "embedding_model": self.settings.embedding_model,
                "reranker_model": self.settings.reranker_model_name,
                "policy_version": "security.policy.v1",
                # Resolve chitchat templates per-user so multi-tenant
                # deployments see the correct school branding. The
                # resolution prefers the user's JWT school_code + roles
                # over the global ``tenant_display_name`` setting, so
                # admins and platform operators get the generic branding
                # while HUST/HUCE users see their school's display name.
                "chitchat_templates": resolve_chitchat_templates(
                    school_code=str(getattr(user, "department", "") or ""),
                    roles=set(
                        getattr(user, "roles", set()) or set()
                    ),
                ),
                # Cache the resolved display name so the LLM generator
                # (which doesn't have direct access to chitchat_templates)
                # can use the same per-user branding in the system prompt.
                "tenant_display_name": resolve_tenant_display_name(
                    school_code=str(getattr(user, "department", "") or ""),
                    roles=set(
                        getattr(user, "roles", set()) or set()
                    ),
                ),
            }
        )
        self._runtime_inputs[current_thread] = runtime_state
        result = await self.graph.ainvoke(runtime_state, config)
        if "__interrupt__" not in result:
            self.observability.finish_trace(result)
        self.retention_policy.prune(self.checkpointer, current_thread)
        return result

    def get_graph_state(self, thread_id: str):
        return self.graph.get_state(self._config(thread_id))

    def get_state_history(self, thread_id: str, *, limit: int | None = None):
        return list(self.graph.get_state_history(self._config(thread_id), limit=limit))

    async def resume_graph(
        self,
        thread_id: str,
        decision: Any | None = None,
    ) -> RetrievalState:
        config = self._config(thread_id)
        runtime = self._runtime_inputs.get(thread_id, {})
        if decision is None:
            result = await self.graph.ainvoke(None, config)
        else:
            result = await self.graph.ainvoke(Command(resume=decision, update=runtime), config)
        self.retention_policy.prune(self.checkpointer, thread_id)
        return result

    async def submit_human_decision(
        self,
        thread_id: str,
        decision: str,
        *,
        actor_id: str,
    ) -> RetrievalState:
        if decision not in {"approve", "reject", "retry"}:
            raise ValueError("Human decision must be approve, reject, or retry.")
        if not actor_id.strip():
            raise ValueError("actor_id is required for human-decision audit.")
        return await self.resume_graph(
            thread_id,
            {
                "decision": decision,
                "actor_id": actor_id,
                "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        )


def build_retrieval_graph(
    settings: RAGSettings,
    retriever: HybridRetriever | None = None,
    reranker_service: Any | None = None,
    generator: AnswerGenerator | None = None,
    context_provider: ContextChunkProvider | None = None,
    **kwargs: Any,
):
    """Compile the fixed retrieval graph; callers cannot supply a bypass edge."""

    return RetrievalWorkflow(
        settings=settings,
        retriever=retriever,
        reranker_service=reranker_service,
        generator=generator,
        context_provider=context_provider,
        **kwargs,
    ).graph


__all__ = ["RetrievalState", "RetrievalWorkflow", "build_retrieval_graph"]
