from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol

from qdrant_client.models import Filter

from src.db.repository import Repository
from src.domain.schemas import (
    Candidate,
    Latency,
    RetrievalResult,
    RetrievalStatus,
    RetrievedChunk,
    UserContext,
)
from src.rag.config import RAGSettings
from src.retrieval.candidate_pool import (
    cap_chunks_per_document,
    clean_candidate_pool,
)
from src.retrieval.heading_context import carry_forward_section_headings
from src.retrieval.keyword import bm25_search, tokenize
from src.retrieval.query_expansion import build_lexical_query
from src.retrieval.query_transform import (
    extract_alphanumeric_identifiers,
    extract_document_numbers,
    extract_form_codes,
    validate_query,
)
from src.retrieval.relevance import (
    contains_requested_numeric_answer,
    corpus_lexical_relevance_scores,
    expects_numeric_answer,
)
from src.retrieval.sparse import SparseRetriever
from src.retrieval.vector_store import VectorStore
from src.security.policy import build_access_filter
from src.services.embeddings import EmbeddingProvider

__all__ = ["cap_chunks_per_document", "filter_candidates_by_explicit_identifiers"]


# ----------------------------------------------------------------------
# Helpers for defensive payload parsing in _audit_candidates.
# ----------------------------------------------------------------------

_LEGAL_STATUSES_DEFAULT = "effective"


def _patch_payload_for_validation(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill in missing optional fields with safe defaults before QdrantPayload validation.

    Legacy chunks indexed before 2026-08 may be missing fields that are
    technically required by the schema but not critical for access decisions.
    We fill them with safe defaults so the payload can still pass
    ``QdrantPayload.model_validate`` and therefore be audited / checked
    for access rather than silently dropped.

    Required fields (``tenant_id``, ``document_id``, ``version_id``,
    ``chunk_id``) are NOT patched — a payload missing any of those is
    genuinely malformed and should still fail validation (logged once).
    """

    def _set(key: str, value: Any) -> None:
        if key not in raw or raw[key] is None or raw[key] == "":
            raw[key] = value

    # Legacy indexing runs may have stored "legal_status" as the filter key
    # even though the canonical schema uses "status". Normalise it.
    if "legal_status" in raw and ("status" not in raw or raw["status"] is None):
        raw["status"] = raw["legal_status"]

    # Fields that are required by QdrantPayload but absent in older records.
    _set("classification", "internal")
    _set("content_hash", f"legacy:{raw.get('chunk_id', 'unknown')}")
    _set("embedding_model", "text-embedding-3-small")
    _set("embedding_version", "1")
    _set("index_version", "pre-2026-08")
    # ``status`` may have been stored as "published" / "effective" etc.
    _set("status", _LEGAL_STATUSES_DEFAULT)

    # Optional but valuable for citation completeness.
    _set("title", raw.get("chunk_id", ""))
    _set("document_number", "")
    _set("section", "")
    _set("page", None)
    _set("owner_unit", "")
    _set("allowed_roles", [])
    _set("allowed_units", [])

    return raw


def filter_candidates_by_explicit_identifiers(
    query: str,
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prevent fallback to unrelated documents when the query names an identifier."""

    document_numbers = extract_document_numbers(query)
    exact_identifiers = [
        *extract_form_codes(query),
        *extract_alphanumeric_identifiers(query),
    ]
    if not document_numbers and not exact_identifiers:
        return candidates

    filtered = list(candidates)
    if document_numbers:
        primary_numbers = {
            value.split("/", 1)[0].casefold() for value in document_numbers
        }
        metadata_matches = []
        for candidate in filtered:
            payload = candidate.get("payload") or {}
            metadata_text = " ".join(
                str(value)
                for value in (
                    payload.get("document_number"),
                    payload.get("title"),
                )
                if value
            ).casefold()
            if any(primary in metadata_text for primary in primary_numbers):
                metadata_matches.append(candidate)
        if metadata_matches:
            filtered = metadata_matches
        else:
            document_aliases = {
                value.casefold() for value in document_numbers
            } | primary_numbers
            filtered = [
                candidate
                for candidate in filtered
                if any(
                    alias
                    in " ".join(
                        str(value)
                        for value in (
                            (candidate.get("payload") or {}).get("document_number"),
                            (candidate.get("payload") or {}).get("title"),
                            candidate.get("embedding_text"),
                            candidate.get("text"),
                        )
                        if value
                    ).casefold()
                    for alias in document_aliases
                )
            ]

    if not exact_identifiers:
        return filtered

    normalized_exact = {value.casefold() for value in exact_identifiers}
    exact_matches = []
    for candidate in filtered:
        payload = candidate.get("payload") or {}
        searchable = " ".join(
            str(value)
            for value in (
                payload.get("document_number"),
                payload.get("title"),
                candidate.get("embedding_text"),
                candidate.get("text"),
            )
            if value
        ).casefold()
        if any(identifier in searchable for identifier in normalized_exact):
            exact_matches.append(candidate)
    return exact_matches


class DenseCandidateRetriever(Protocol):
    async def dense_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]: ...


class SparseCandidateRetriever(Protocol):
    async def sparse_search(
        self,
        query: str,
        access_filter: Filter,
        limit: int,
        index_version: str,
    ) -> list[Candidate]: ...


@dataclass(frozen=True)
class _LegOutcome:
    candidates: list[Candidate]
    latency_ms: float
    warning: str | None = None


logger = logging.getLogger(__name__)


def merge_candidate_metadata(*candidates: Candidate) -> dict[str, Any]:
    """Merge metadata without using incomparable dense/sparse raw scores for rank."""

    merged: dict[str, Any] = {}
    conflicts: set[str] = set()
    sources: set[str] = set()
    for candidate in candidates:
        if candidate.dense_rank is not None:
            sources.add("dense")
        if candidate.sparse_rank is not None:
            sources.add("sparse")
        for key, value in candidate.metadata.items():
            if key not in merged:
                merged[key] = value
            elif merged[key] != value:
                conflicts.add(key)
    if sources:
        merged["retrieval_sources"] = sorted(sources)
    if conflicts:
        merged["metadata_conflicts"] = sorted(conflicts)
    return merged


def _merge_candidates(first: Candidate, second: Candidate) -> Candidate:
    if (
        first.document_id != second.document_id
        or first.version_id != second.version_id
        or first.content != second.content
    ):
        raise ValueError(
            f"Conflicting immutable data for duplicate chunk_id {first.chunk_id}."
        )
    dense_ranks = [rank for rank in (first.dense_rank, second.dense_rank) if rank]
    sparse_ranks = [rank for rank in (first.sparse_rank, second.sparse_rank) if rank]
    rerank_scores = [
        score for score in (first.rerank_score, second.rerank_score) if score is not None
    ]
    return first.model_copy(
        update={
            "metadata": merge_candidate_metadata(first, second),
            "dense_rank": min(dense_ranks, default=None),
            "sparse_rank": min(sparse_ranks, default=None),
            "fusion_score": max(first.fusion_score, second.fusion_score),
            "rerank_score": max(rerank_scores, default=None),
        }
    )


def deduplicate_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_chunk_id: dict[str, Candidate] = {}
    order: list[str] = []
    for candidate in candidates:
        existing = by_chunk_id.get(candidate.chunk_id)
        if existing is None:
            by_chunk_id[candidate.chunk_id] = candidate.model_copy(
                update={"metadata": merge_candidate_metadata(candidate)}
            )
            order.append(candidate.chunk_id)
        else:
            by_chunk_id[candidate.chunk_id] = _merge_candidates(existing, candidate)
    return [by_chunk_id[chunk_id] for chunk_id in order]


def _fuse(
    dense_candidates: list[Candidate],
    sparse_candidates: list[Candidate],
    *,
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
) -> list[Candidate]:
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive.")
    if dense_weight < 0 or sparse_weight < 0 or dense_weight + sparse_weight == 0:
        raise ValueError("RRF weights must be non-negative and not both zero.")

    dense = deduplicate_candidates(dense_candidates)
    sparse = deduplicate_candidates(sparse_candidates)
    merged = {
        candidate.chunk_id: candidate
        for candidate in deduplicate_candidates([*dense, *sparse])
    }
    scores: dict[str, float] = {chunk_id: 0.0 for chunk_id in merged}
    best_rank: dict[str, int] = {}

    for position, candidate in enumerate(dense, start=1):
        rank = candidate.dense_rank or position
        scores[candidate.chunk_id] += dense_weight / (rrf_k + rank)
        best_rank[candidate.chunk_id] = min(best_rank.get(candidate.chunk_id, rank), rank)
    for position, candidate in enumerate(sparse, start=1):
        rank = candidate.sparse_rank or position
        scores[candidate.chunk_id] += sparse_weight / (rrf_k + rank)
        best_rank[candidate.chunk_id] = min(best_rank.get(candidate.chunk_id, rank), rank)

    fused = [
        candidate.model_copy(update={"fusion_score": scores[chunk_id]})
        for chunk_id, candidate in merged.items()
    ]
    return sorted(
        fused,
        key=lambda candidate: (
            -candidate.fusion_score,
            best_rank[candidate.chunk_id],
            candidate.chunk_id,
        ),
    )


def rrf_fuse(
    dense_candidates: list[Candidate],
    sparse_candidates: list[Candidate],
    *,
    rrf_k: int = 60,
) -> list[Candidate]:
    """Balanced RRF; raw cosine and sparse scores are never added together."""

    return _fuse(
        dense_candidates,
        sparse_candidates,
        rrf_k=rrf_k,
        dense_weight=1.0,
        sparse_weight=1.0,
    )


def weighted_rrf_fuse(
    dense_candidates: list[Candidate],
    sparse_candidates: list[Candidate],
    *,
    dense_weight: float,
    sparse_weight: float,
    rrf_k: int = 60,
) -> list[Candidate]:
    """Optional weighted RRF. Checkpoint 6 keeps balanced ``rrf_fuse`` as default."""

    return _fuse(
        dense_candidates,
        sparse_candidates,
        rrf_k=rrf_k,
        dense_weight=dense_weight,
        sparse_weight=sparse_weight,
    )


async def _run_leg(
    name: str,
    retrieval: Awaitable[list[Candidate]],
    *,
    timeout_seconds: float,
) -> _LegOutcome:
    started = time.perf_counter()
    try:
        candidates = await asyncio.wait_for(retrieval, timeout=timeout_seconds)
        return _LegOutcome(
            candidates=candidates,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
    except TimeoutError:
        return _LegOutcome(
            candidates=[],
            latency_ms=(time.perf_counter() - started) * 1000,
            warning=f"{name.capitalize()} retrieval timed out.",
        )
    except Exception as exc:  # noqa: BLE001 - a failed leg must not fail the other leg
        return _LegOutcome(
            candidates=[],
            latency_ms=(time.perf_counter() - started) * 1000,
            warning=f"{name.capitalize()} retrieval failed ({type(exc).__name__}).",
        )


async def hybrid_retrieve(
    query: str,
    user_context: UserContext,
    index_version: str,
    *,
    dense_retriever: DenseCandidateRetriever,
    sparse_retriever: SparseCandidateRetriever,
    settings: RAGSettings,
    transformed_queries: list[str] | None = None,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> RetrievalResult:
    validate_query(query)
    if not index_version.strip():
        raise ValueError("index_version must not be blank.")
    started = time.perf_counter()
    policy_started = time.perf_counter()
    access_filter = build_access_filter(
        user_context,
        as_of=as_of,
        include_historical=include_historical,
    )
    policy_ms = (time.perf_counter() - policy_started) * 1000
    leg_limit = settings.fused_limit

    dense_outcome, sparse_outcome = await asyncio.gather(
        _run_leg(
            "dense",
            dense_retriever.dense_search(
                query,
                access_filter,
                leg_limit,
                index_version,
            ),
            timeout_seconds=settings.retrieval_leg_timeout_seconds,
        ),
        _run_leg(
            "sparse",
            sparse_retriever.sparse_search(
                query,
                access_filter,
                leg_limit,
                index_version,
            ),
            timeout_seconds=settings.retrieval_leg_timeout_seconds,
        ),
    )

    warnings = [
        warning
        for warning in (dense_outcome.warning, sparse_outcome.warning)
        if warning is not None
    ]
    if dense_outcome.warning is None and not dense_outcome.candidates:
        warnings.append("Dense retrieval returned no candidates.")
    if sparse_outcome.warning is None and not sparse_outcome.candidates:
        warnings.append("Sparse retrieval returned no candidates.")

    fusion_started = time.perf_counter()
    fused = rrf_fuse(
        dense_outcome.candidates,
        sparse_outcome.candidates,
        rrf_k=settings.rrf_k,
    )
    selected = clean_candidate_pool(
        fused,
        limit=settings.fused_limit,
        max_chunks_per_document=settings.max_chunks_per_document,
        near_duplicate_threshold=settings.near_duplicate_similarity_threshold,
    )
    fusion_ms = (time.perf_counter() - fusion_started) * 1000

    failed_legs = sum(
        outcome.warning is not None for outcome in (dense_outcome, sparse_outcome)
    )
    empty_legs = sum(
        not outcome.candidates for outcome in (dense_outcome, sparse_outcome)
    )
    if not selected:
        status = RetrievalStatus.NOT_FOUND
    elif failed_legs or empty_legs:
        status = RetrievalStatus.PARTIAL
    else:
        status = RetrievalStatus.SUFFICIENT

    total_ms = (time.perf_counter() - started) * 1000
    # Structured latency log — use this to tune per-leg budgets in RAGSettings.
    # Target total for RAG + GPT-4o-mini: 3–6 s. If dense_ms > 3 s, check
    # embedding cache / Qdrant connection. If sparse_ms > 1 s, check BM25.
    logger.info(
        "hybrid_retrieve_latency query_len=%d tenant=%s dept=%s "
        "policy_ms=%.1f dense_ms=%.1f sparse_ms=%.1f fusion_ms=%.1f total_ms=%.1f "
        "candidates=%d status=%s warnings=%s",
        len(query),
        user_context.tenant_id,
        user_context.department,
        policy_ms,
        dense_outcome.latency_ms,
        sparse_outcome.latency_ms,
        fusion_ms,
        total_ms,
        len(selected),
        status.value,
        warnings,
    )
    return RetrievalResult(
        status=status,
        original_query=query,
        transformed_queries=transformed_queries or [],
        candidates=selected,
        warnings=warnings,
        latency=Latency(
            policy_filter_ms=policy_ms,
            dense_ms=dense_outcome.latency_ms,
            sparse_ms=sparse_outcome.latency_ms,
            fusion_ms=fusion_ms,
            total_ms=total_ms,
        ),
        index_version=index_version,
    )


class HybridRetriever:
    def __init__(
        self,
        settings: RAGSettings,
        repository: Repository,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        sparse_retriever: SparseRetriever | None = None,
    ):
        self.settings = settings
        self.repository = repository
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.sparse_retriever = sparse_retriever

    async def search(
        self,
        query: str,
        user: UserContext,
        as_of_date: date | None = None,
        *,
        embed_text: str | None = None,
        evaluation_trace: dict[str, Any] | None = None,
    ) -> list[RetrievedChunk]:
        """Retrieve authorized chunks, optionally exposing evaluation-only stage data.

        ``evaluation_trace`` is an opt-in diagnostic sink for offline evaluation.
        It never changes ranking and is intentionally absent from API responses and
        production logs.  The caller must treat its contents as sensitive because
        they contain chunk identifiers.
        """
        started = time.perf_counter()
        candidates = carry_forward_section_headings(
            sorted(
                self.repository.list_searchable_chunks(user, as_of_date),
                key=lambda item: (
                    str((item.get("payload") or {}).get("document_id") or ""),
                    str((item.get("payload") or {}).get("version_id") or ""),
                    int((item.get("payload") or {}).get("chunk_index") or 0),
                ),
            )
        )
        candidates_filter_ms = (time.perf_counter() - started) * 1000
        # Always filter by identifiers from the original query so that
        # "Quyết định 7737" still gates retrieval. When a HyDE passage is
        # supplied (embed_text != None) we embed that for dense retrieval
        # instead of the query text — the passage is richer in chunk vocabulary.
        candidates = filter_candidates_by_explicit_identifiers(query, candidates)
        if evaluation_trace is not None:
            evaluation_trace.update(
                {
                    "authorized_candidate_ids": [item["chunk_id"] for item in candidates],
                    "dense_chunk_ids": [],
                    "sparse_chunk_ids": [],
                    "bm25_chunk_ids": [],
                    "fused_chunk_ids": [],
                    "reranked_chunk_ids": [],
                    "latency_ms": {"policy_filter": candidates_filter_ms},
                }
            )
        if not candidates:
            if evaluation_trace is not None:
                evaluation_trace["latency_ms"]["total"] = (
                    time.perf_counter() - started
                ) * 1000
            logger.info(
                "hybrid_retriever_no_candidates query_len=%d tenant=%s dept=%s "
                "filter_ms=%.1f",
                len(query),
                user.tenant_id,
                user.department,
                candidates_filter_ms,
            )
            return []

        # Opaque identifiers (student/application codes) are exact keys, not
        # semantic concepts. The identifier filter above has already applied
        # the repository access scope; return the matching rows before paying
        # for embeddings or allowing vector similarity to dilute the match.
        exact_ids = extract_alphanumeric_identifiers(query)
        if exact_ids:
            ranked_exact = sorted(
                candidates,
                key=lambda item: self._exact_identifier_rank(query, item),
                reverse=True,
            )
            output = [
                RetrievedChunk(
                    chunk_id=item["chunk_id"],
                    text=item["text"],
                    score=score,
                    source="exact_identifier",
                    metadata=item["payload"],
                )
                for item in ranked_exact[: self.settings.final_top_k]
                if (score := self._exact_identifier_rank(query, item)) > 0
            ]
            if evaluation_trace is not None:
                exact_chunk_ids = [item.chunk_id for item in output]
                evaluation_trace["fused_chunk_ids"] = exact_chunk_ids
                evaluation_trace["reranked_chunk_ids"] = exact_chunk_ids
                evaluation_trace["latency_ms"]["total"] = (
                    time.perf_counter() - started
                ) * 1000
            return output

        by_id = {item["chunk_id"]: item for item in candidates}
        allowed_ids = set(by_id)
        access_filter = build_access_filter(user, as_of=as_of_date)
        lexical_query = (
            build_lexical_query(
                query,
                max_extra=self.settings.query_expansion_max_extra,
            )
            if self.settings.query_expansion_enabled
            else query
        )
        # Embed the passage (HyDE) or the original query for dense retrieval.
        vector_source = embed_text if embed_text else query
        embed_started = time.perf_counter()
        query_vector = await self.embeddings.embed_query(vector_source)
        embed_ms = (time.perf_counter() - embed_started) * 1000

        # Run dense, Qdrant sparse, and corpus-local BM25 legs in parallel.
        # Qdrant sparse can miss exact table rows when the deployed sparse index
        # lags the authoritative PostgreSQL corpus. Local BM25 is therefore an
        # independent lexical safety net over the already access-filtered rows.
        async def _sparse_search() -> list[tuple[str, float, dict]]:
            if self.sparse_retriever is not None:
                sparse_query = self.sparse_retriever.embedding_provider.sparse_embed_query(
                    lexical_query
                )
                try:
                    return await self.vector_store.search_sparse(
                        sparse_query,
                        limit=self.settings.keyword_top_k,
                        allowed_ids=allowed_ids,
                        query_filter=access_filter,
                    )
                except Exception as exc:  # noqa: BLE001 - sparse leg must not break dense
                    logger.warning(
                        "sparse_retrieval_failed query_len=%d reason=%s",
                        len(query),
                        type(exc).__name__,
                    )
                    return []
            else:
                return []

        search_started = time.perf_counter()
        semantic_results, sparse_results, bm25_results = await asyncio.gather(
            self.vector_store.search(
                query_vector,
                limit=self.settings.semantic_top_k,
                allowed_ids=allowed_ids,
                query_filter=access_filter,
            ),
            _sparse_search(),
            asyncio.to_thread(
                bm25_search,
                lexical_query,
                candidates,
                limit=self.settings.keyword_top_k,
            ),
        )
        search_ms = (time.perf_counter() - search_started) * 1000

        if evaluation_trace is not None:
            evaluation_trace["dense_chunk_ids"] = [item[0] for item in semantic_results]
            evaluation_trace["sparse_chunk_ids"] = [item[0] for item in sparse_results]
            evaluation_trace["bm25_chunk_ids"] = [item[0] for item in bm25_results]

        self._audit_candidates(user, semantic_results)

        fusion_started = time.perf_counter()
        fused, sources = self._weighted_rrf_with_local_bm25(
            semantic_results,
            sparse_results,
            bm25_results,
        )
        fusion_ms = (time.perf_counter() - fusion_started) * 1000
        fused_chunk_ids = [
            chunk_id
            for chunk_id, _score in sorted(
                fused.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

        rerank_started = time.perf_counter()
        # Expansion helps recall in sparse retrieval, but ranking must stay
        # anchored to the user's actual wording. Ranking on appended generic
        # phrases (for example "học phí sau đại học") over-promotes headings.
        reranked = self._rerank(query, fused, by_id)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
        if evaluation_trace is not None:
            evaluation_trace["fused_chunk_ids"] = fused_chunk_ids
            evaluation_trace["reranked_chunk_ids"] = [
                chunk_id for chunk_id, _score in reranked
            ]
            evaluation_trace["retrieved_scores"] = {
                chunk_id: score for chunk_id, score in reranked
            }
            evaluation_trace["latency_ms"].update(
                {
                    "embedding": embed_ms,
                    "search": search_ms,
                    "fusion": fusion_ms,
                    "rerank": rerank_ms,
                }
            )
        logger.info(
            "hybrid_retriever_top_candidates top=%s",
            [
                (chunk_id, round(score, 3))
                for chunk_id, score in reranked[:5]
            ],
        )
        output: list[RetrievedChunk] = []
        for chunk_id, score in reranked[: self.settings.final_top_k]:
            item = by_id[chunk_id]
            output.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=item["text"],
                    score=score,
                    source="+".join(sorted(sources.get(chunk_id, {"keyword"}))),
                    metadata=item["payload"],
                )
            )
        total_ms = (time.perf_counter() - started) * 1000
        if evaluation_trace is not None:
            evaluation_trace["latency_ms"]["total"] = total_ms
        # Structured latency log for the HybridRetriever.search path.
        # Use this to tune the per-leg settings. Target: total < 1.5 s.
        logger.info(
            "hybrid_retriever_search_latency query_len=%d tenant=%s dept=%s "
            "filter_ms=%.1f embed_ms=%.1f search_ms=%.1f fusion_ms=%.1f rerank_ms=%.1f total_ms=%.1f "
            "candidates_in=%d candidates_out=%d",
            len(query),
            user.tenant_id,
            user.department,
            candidates_filter_ms,
            embed_ms,
            search_ms,
            fusion_ms,
            rerank_ms,
            total_ms,
            len(by_id),
            len(output),
        )
        return output

    @staticmethod
    def _exact_identifier_rank(query: str, item: dict[str, Any]) -> float:
        identifiers = {
            value.casefold() for value in extract_alphanumeric_identifiers(query)
        }
        searchable = " ".join(
            str(value)
            for value in (
                item.get("text"),
                item.get("embedding_text"),
                (item.get("payload") or {}).get("title"),
            )
            if value
        ).casefold()
        matched = sum(identifier in searchable for identifier in identifiers)
        if not matched:
            return 0.0
        query_tokens = set(tokenize(query))
        content_tokens = set(tokenize(searchable))
        overlap = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
        return min(0.9 + (0.1 * overlap), 1.0)

    def _audit_candidates(self, user: UserContext, semantic_results) -> None:
        from src.domain.schemas import QdrantPayload
        from src.security.policy import audit_access_decision, can_access_document

        if not semantic_results:
            return
        patched_payload_count = 0
        invalid_payload_count = 0
        audit_failure_count = 0
        for chunk_id, _score, raw_payload in semantic_results:
            try:
                # Try strict validation first — this is the common path for
                # post-2026-08 indexed chunks.
                payload = QdrantPayload.model_validate(raw_payload)
            except Exception as exc:
                # Legacy chunks may be missing optional fields. Patch them and
                # retry once so we still audit + check access instead of
                # silently dropping the candidate.
                patched = _patch_payload_for_validation(dict(raw_payload))
                try:
                    payload = QdrantPayload.model_validate(patched)
                    patched_payload_count += 1
                    logger.warning(
                        "qdrant_payload_patched chunk_id=%s original_error=%s",
                        chunk_id,
                        type(exc).__name__,
                    )
                except Exception as patch_exc:
                    # Even the patched payload is malformed — genuinely bad data.
                    # Log once and skip; do NOT crash retrieval.
                    invalid_payload_count += 1
                    logger.warning(
                        "qdrant_payload_invalid chunk_id=%s reason=%s",
                        chunk_id,
                        type(patch_exc).__name__,
                    )
                    continue
            allowed = can_access_document(user, payload)
            try:
                audit_access_decision(
                    self.repository,
                    request_id=getattr(user, "request_id", "search"),
                    user=user,
                    document=payload,
                    allowed=allowed,
                    reason="retrieval access decision",
                )
            except Exception as exc:
                # Audit failure must not break retrieval (the user still
                # gets their answer), but it MUST be logged loudly —
                # missing audit rows are a compliance risk. See
                # BUGS_FOUND.md follow-up to B-P3-02.
                audit_failure_count += 1
                logger.error(
                    "audit_access_decision_failed chunk_id=%s reason=%s",
                    chunk_id,
                    type(exc).__name__,
                )
                continue
        if patched_payload_count or invalid_payload_count or audit_failure_count:
            logger.info(
                "hybrid_audit_summary patched_payloads=%d invalid_payloads=%d audit_failures=%d",
                patched_payload_count,
                invalid_payload_count,
                audit_failure_count,
            )

    def _weighted_rrf(
        self,
        semantic_results: list[tuple[str, float, dict]],
        keyword_results,
    ) -> tuple[dict[str, float], dict[str, set[str]]]:
        """Fuse dense and sparse/keyword ranks; alpha is the dense-search weight."""
        alpha = self.settings.rrf_alpha
        fused: dict[str, float] = {}
        sources: dict[str, set[str]] = {}
        for rank, (chunk_id, _score, _payload) in enumerate(semantic_results, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + alpha / (self.settings.rrf_k + rank)
            sources.setdefault(chunk_id, set()).add("semantic")
        for rank, item in enumerate(keyword_results, start=1):
            if isinstance(item, tuple) and len(item) >= 2:
                chunk_id = item[0]
            else:
                chunk_id = item
            fused[chunk_id] = fused.get(chunk_id, 0.0) + (1 - alpha) / (
                self.settings.rrf_k + rank
            )
            sources.setdefault(chunk_id, set()).add("keyword")
        return fused, sources

    def _weighted_rrf_with_local_bm25(
        self,
        semantic_results: list[tuple[str, float, dict]],
        sparse_results: list[tuple[str, float, dict]],
        bm25_results: list[tuple[str, float]],
    ) -> tuple[dict[str, float], dict[str, set[str]]]:
        """Fuse dense retrieval with two independent lexical rankings."""

        alpha = self.settings.rrf_alpha
        lexical_weight = (1 - alpha) / 2
        fused: dict[str, float] = {}
        sources: dict[str, set[str]] = {}

        rankings = (
            (semantic_results, alpha, "semantic"),
            (sparse_results, lexical_weight, "sparse"),
            (bm25_results, lexical_weight, "bm25"),
        )
        for ranking, weight, source in rankings:
            for rank, item in enumerate(ranking, start=1):
                chunk_id = item[0]
                fused[chunk_id] = fused.get(chunk_id, 0.0) + weight / (
                    self.settings.rrf_k + rank
                )
                sources.setdefault(chunk_id, set()).add(source)
        return fused, sources

    def _rerank(
        self,
        query: str,
        fused: dict[str, float],
        by_id: dict[str, dict],
    ) -> list[tuple[str, float]]:
        maximum_fused = max(fused.values(), default=1.0)
        chunk_ids = list(fused)
        lexical_scores = corpus_lexical_relevance_scores(
            query,
            [
                by_id[chunk_id].get("embedding_text")
                or by_id[chunk_id]["text"]
                for chunk_id in chunk_ids
            ],
            [by_id[chunk_id].get("payload") or {} for chunk_id in chunk_ids],
        )
        if expects_numeric_answer(query):
            lexical_scores = [
                score
                if contains_requested_numeric_answer(
                    query,
                    by_id[chunk_id].get("embedding_text")
                    or by_id[chunk_id]["text"],
                )
                else 0.0
                for chunk_id, score in zip(chunk_ids, lexical_scores, strict=True)
            ]
        results: list[tuple[str, float]] = []
        for chunk_id, lexical_score in zip(
            chunk_ids,
            lexical_scores,
            strict=True,
        ):
            rrf_score = fused[chunk_id]
            normalized_rrf = rrf_score / maximum_fused
            final_score = 0.40 * normalized_rrf + 0.60 * lexical_score
            results.append((chunk_id, min(final_score, 1.0)))
        return sorted(results, key=lambda item: item[1], reverse=True)
