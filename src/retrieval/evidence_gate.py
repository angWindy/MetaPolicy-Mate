from __future__ import annotations

import math
import time
from collections.abc import Sequence

from src.domain.schemas import (
    Candidate,
    Citation,
    EvidenceAction,
    EvidenceAssessment,
    Latency,
    RerankResult,
    RetrievalStatus,
)
from src.rag.config import EvidenceThresholds, RAGSettings

_CURRENT_LEGAL_STATUSES = {"effective"}
_CITATION_KEYS = ("document_number", "title")


def _score(candidate: Candidate) -> float | None:
    score = candidate.rerank_score
    if score is None or not math.isfinite(score):
        return None
    return float(score)


def _source_identity(candidate: Candidate) -> str:
    metadata = candidate.metadata
    return str(
        metadata.get("independent_source_id")
        or metadata.get("source_id")
        or candidate.document_id
    ).strip()


def count_independent_sources(candidates: Sequence[Candidate]) -> int:
    """Count source families, not chunks or versions of the same document."""

    return len({_source_identity(candidate) for candidate in candidates if _source_identity(candidate)})


def _locator(candidate: Candidate) -> tuple[str, str, str, str]:
    metadata = candidate.metadata
    return (
        str(metadata.get("document_number") or candidate.document_id).casefold(),
        str(metadata.get("article") or "").casefold(),
        str(metadata.get("clause") or "").casefold(),
        str(metadata.get("point") or "").casefold(),
    )


def _normalized_content(candidate: Candidate) -> str:
    return " ".join(candidate.content.casefold().split())


def detect_conflicts(candidates: Sequence[Candidate]) -> list[str]:
    """Return deterministic conflict reasons without deciding which text is correct."""

    reasons: list[str] = []
    by_locator: dict[tuple[str, str, str, str], list[Candidate]] = {}
    for candidate in candidates:
        metadata = candidate.metadata
        explicit = metadata.get("conflicts_with") or metadata.get("conflict_chunk_ids")
        metadata_conflicts = metadata.get("metadata_conflicts")
        if explicit:
            reasons.append(f"{candidate.chunk_id} declares a conflict with {explicit}.")
        if metadata_conflicts:
            reasons.append(
                f"{candidate.chunk_id} has conflicting metadata fields: {metadata_conflicts}."
            )
        by_locator.setdefault(_locator(candidate), []).append(candidate)

    for locator, group in by_locator.items():
        effective = [
            candidate
            for candidate in group
            if str(candidate.metadata.get("legal_status") or "").casefold()
            in _CURRENT_LEGAL_STATUSES
        ]
        if (
            len({candidate.version_id for candidate in effective}) > 1
            and len({_normalized_content(candidate) for candidate in effective}) > 1
        ):
            reasons.append(
                "Multiple effective versions disagree at " + "/".join(locator) + "."
            )
    return list(dict.fromkeys(reasons))


def should_retry(
    status: RetrievalStatus,
    retry_count: int,
    max_retries: int,
) -> bool:
    return status is RetrievalStatus.WEAK and retry_count < max_retries


def should_abstain(
    status: RetrievalStatus,
    retry_count: int = 0,
    max_retries: int = 0,
) -> bool:
    if status in {RetrievalStatus.NOT_FOUND, RetrievalStatus.FORBIDDEN, RetrievalStatus.PARTIAL}:
        return True
    return status is RetrievalStatus.WEAK and not should_retry(status, retry_count, max_retries)


def build_evidence_reason(
    status: RetrievalStatus,
    *,
    top_score: float | None,
    score_gap: float | None,
    independent_sources: int,
    citation_complete: bool,
    versions_current: bool,
    conflict_reasons: Sequence[str] = (),
    retry_count: int = 0,
    max_retries: int = 0,
) -> str:
    details = [
        f"status={status.value}",
        f"top_score={top_score if top_score is not None else 'unavailable'}",
        f"score_gap={score_gap if score_gap is not None else 'unavailable'}",
        f"independent_sources={independent_sources}",
        f"citation_metadata={'complete' if citation_complete else 'incomplete'}",
        f"versions={'current' if versions_current else 'not_current_or_unknown'}",
    ]
    if status is RetrievalStatus.FORBIDDEN:
        details.append("access is forbidden and retry is disabled")
    elif status is RetrievalStatus.NOT_FOUND:
        details.append("no evidence is available; generation is disabled")
    elif status is RetrievalStatus.CONFLICT:
        details.append("human review required: " + "; ".join(conflict_reasons))
    elif status is RetrievalStatus.WEAK:
        details.append(f"retry={retry_count}/{max_retries}")
    elif status is RetrievalStatus.PARTIAL:
        details.append("evidence is incomplete; generation is disabled")
    else:
        details.append("evidence meets the configured domain thresholds")
    return "; ".join(details)


def _citation_complete(candidate: Candidate) -> bool:
    metadata = candidate.metadata
    return all(str(metadata.get(key) or "").strip() for key in _CITATION_KEYS) and bool(
        metadata.get("source_url")
        or metadata.get("article")
        or metadata.get("section")
        or metadata.get("page")
    )


def _versions_current(candidates: Sequence[Candidate]) -> bool:
    return bool(candidates) and all(
        str(candidate.metadata.get("legal_status") or "").casefold()
        in _CURRENT_LEGAL_STATUSES
        for candidate in candidates
    )


def _citation(candidate: Candidate) -> Citation:
    metadata = candidate.metadata
    document_number = str(metadata["document_number"])
    title = str(metadata["title"])
    locator = str(metadata.get("section") or metadata.get("article") or "").strip()
    return Citation(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        document_number=document_number,
        title=title,
        source=", ".join(part for part in (document_number, locator) if part),
        article=metadata.get("article"),
        clause=metadata.get("clause"),
        point=metadata.get("point"),
        page=metadata.get("page"),
        source_url=metadata.get("source_url"),
        excerpt=candidate.content[:500],
        rerank_score=candidate.rerank_score,
    )


def _decision(
    status: RetrievalStatus,
    retry_count: int,
    max_retries: int,
    candidate_count: int,
) -> EvidenceAction:
    """Map rerank evidence to the only legal workflow routing.

    Stricter 2026-09-01 contract:
      * SUFFICIENT requires at least 2 selected candidates. A single
        chunk is downgraded to PARTIAL so the citation validator can
        flag it (and warn the operator about a thin evidence base).
      * PARTIAL with 0 selected candidates is an automatic abstain
        (nothing to cite). PARTIAL with ≥1 still generates — the
        citation validator enforces the minimum citation count.
      * CONFLICT always escalates to a human reviewer.
      * Anything else is either retried (until max_retries) or
        abstained.
    """

    if status is RetrievalStatus.SUFFICIENT and candidate_count >= 2:
        return EvidenceAction.GENERATE
    if status is RetrievalStatus.PARTIAL and candidate_count >= 1:
        return EvidenceAction.GENERATE
    if status is RetrievalStatus.CONFLICT:
        return EvidenceAction.HUMAN_ESCALATION
    if should_retry(status, retry_count, max_retries):
        return EvidenceAction.RETRY
    return EvidenceAction.ABSTAIN


def evaluate_evidence(
    result: RerankResult,
    settings: RAGSettings,
    *,
    domain: str | None = None,
    retry_count: int = 0,
) -> EvidenceAssessment:
    """Evaluate reranked evidence and make the only generation routing decision."""

    started = time.perf_counter()
    thresholds: EvidenceThresholds = settings.evidence_thresholds(domain)
    candidates = list(result.candidates)
    scores = sorted((score for item in candidates if (score := _score(item)) is not None), reverse=True)
    top_score = scores[0] if scores else None
    score_gap = scores[0] - scores[1] if len(scores) > 1 else (math.inf if scores else None)
    source_count = count_independent_sources(candidates)
    citation_complete = bool(candidates) and all(_citation_complete(item) for item in candidates)
    versions_current = _versions_current(candidates)
    conflicts = detect_conflicts(candidates)

    if result.status is RetrievalStatus.FORBIDDEN:
        status = RetrievalStatus.FORBIDDEN
    elif conflicts or result.status is RetrievalStatus.CONFLICT:
        status = RetrievalStatus.CONFLICT
        if not conflicts:
            conflicts = ["The upstream retrieval or rerank stage reported a conflict."]
    elif result.status is RetrievalStatus.NOT_FOUND or not candidates:
        status = RetrievalStatus.NOT_FOUND
    elif result.status is RetrievalStatus.PARTIAL:
        # The reranker reported PARTIAL (e.g. no cross-encoder scores).
        # Do NOT demote to WEAK just because top_score is None; treat
        # PARTIAL as a signal to attempt generation with the available
        # fusion-ranked candidates.
        status = RetrievalStatus.PARTIAL
    elif top_score is None or top_score < thresholds.partial_top_score:
        status = RetrievalStatus.WEAK
    elif (
        top_score >= thresholds.sufficient_top_score
        and (score_gap is not None and score_gap >= thresholds.minimum_score_gap)
        and source_count >= thresholds.minimum_independent_sources
        and (citation_complete or not thresholds.require_citation_metadata)
        and versions_current
    ):
        status = RetrievalStatus.SUFFICIENT
    else:
        status = RetrievalStatus.PARTIAL

    decision = _decision(
        status,
        retry_count,
        thresholds.max_retries,
        len(candidates),
    )
    reason = build_evidence_reason(
        status,
        top_score=top_score,
        score_gap=score_gap,
        independent_sources=source_count,
        citation_complete=citation_complete,
        versions_current=versions_current,
        conflict_reasons=conflicts,
        retry_count=retry_count,
        max_retries=thresholds.max_retries,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    selected = candidates if decision is EvidenceAction.GENERATE else []
    citations = [_citation(item) for item in selected if _citation_complete(item)]
    warnings = list(result.warnings)
    if decision is not EvidenceAction.GENERATE:
        warnings.append(reason)
    return EvidenceAssessment(
        status=status,
        decision=decision,
        reason=reason,
        original_query=result.original_query,
        evidence_score=min(max(top_score or 0.0, 0.0), 1.0),
        top_score=top_score,
        score_gap=None if score_gap == math.inf else score_gap,
        independent_sources=source_count,
        retry_count=retry_count,
        selected_candidates=selected,
        citations=citations,
        warnings=list(dict.fromkeys(warnings)),
        latency=Latency(evidence_gate_ms=elapsed_ms, total_ms=elapsed_ms),
    )
