from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from src.domain.schemas import (
    Candidate,
    Citation,
    CitationKind,
    ContextExpansionType,
    ContextRole,
    ContextSegment,
    ContextWindow,
    QdrantPayload,
    UserContext,
)
from src.security.policy import can_access_document

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class AuthoritativeChunk:
    """Chunk content and access metadata read from PostgreSQL."""

    candidate: Candidate
    access_payload: QdrantPayload


class ContextChunkProvider(Protocol):
    """Read-only PostgreSQL boundary; Qdrant must not supply expansion content."""

    def get_context_chunks(
        self,
        chunk_ids: Sequence[str],
    ) -> Mapping[str, AuthoritativeChunk]: ...


def _default_token_counter(text: str) -> int:
    return len(re.findall(r"\S+", text, flags=re.UNICODE))


def _heading_text(candidate: Candidate) -> str:
    metadata = candidate.metadata
    raw_path = metadata.get("heading_path")
    path = (
        [str(item).strip() for item in raw_path if str(item).strip()]
        if isinstance(raw_path, list)
        else []
    )
    if not path and metadata.get("section"):
        path = [str(metadata["section"]).strip()]
    title = str(metadata.get("title") or "").strip()
    parts = [part for part in [title, " > ".join(path)] if part]
    return "\n".join(dict.fromkeys(parts))


def _segment(
    candidate: Candidate,
    *,
    winning_chunk_id: str,
    role: ContextRole,
    expansion_type: ContextExpansionType,
    content: str | None = None,
) -> ContextSegment:
    metadata = {
        **candidate.metadata,
        "supporting_context": role == ContextRole.SUPPORTING_CONTEXT,
        "context_role": role.value,
        "expansion_type": expansion_type.value,
        "winning_chunk_id": winning_chunk_id,
        # Forward rerank_score so citation_validator can extract it
        "rerank_score": candidate.rerank_score,
    }
    return ContextSegment(
        chunk_id=candidate.chunk_id,
        document_id=candidate.document_id,
        version_id=candidate.version_id,
        content=content or candidate.content,
        context_role=role,
        expansion_type=expansion_type,
        winning_chunk_id=winning_chunk_id,
        metadata=metadata,
    )


def _winning_segment(candidate: Candidate) -> ContextSegment:
    heading = _heading_text(candidate)
    content = "\n".join(part for part in [heading, candidate.content] if part)
    return _segment(
        candidate,
        winning_chunk_id=candidate.chunk_id,
        role=ContextRole.WINNING,
        expansion_type=ContextExpansionType.WINNING,
        content=content,
    )


def _authorized_support(
    record: AuthoritativeChunk | None,
    *,
    winning: Candidate,
    user: UserContext,
    as_of: date | datetime | None,
    include_historical: bool,
) -> Candidate | None:
    if record is None:
        return None
    candidate = record.candidate
    payload = record.access_payload
    if (
        candidate.chunk_id != payload.chunk_id
        or candidate.document_id != payload.document_id
        or candidate.version_id != payload.version_id
    ):
        return None
    if (
        candidate.document_id != winning.document_id
        or candidate.version_id != winning.version_id
    ):
        return None
    if not can_access_document(
        user,
        payload,
        as_of=as_of,
        include_historical=include_historical,
    ):
        return None
    return candidate


def expand_parent_context(
    winning: Candidate,
    *,
    provider: ContextChunkProvider,
    user: UserContext,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> list[ContextSegment]:
    parent_id = winning.metadata.get("parent_chunk_id")
    if isinstance(parent_id, str) and parent_id.strip():
        records = provider.get_context_chunks([parent_id])
        parent = _authorized_support(
            records.get(parent_id),
            winning=winning,
            user=user,
            as_of=as_of,
            include_historical=include_historical,
        )
        if parent is not None:
            return [
                _segment(
                    parent,
                    winning_chunk_id=winning.chunk_id,
                    role=ContextRole.SUPPORTING_CONTEXT,
                    expansion_type=ContextExpansionType.PARENT_CHUNK,
                )
            ]

    heading = _heading_text(winning)
    if not heading:
        return []
    return [
        _segment(
            winning,
            winning_chunk_id=winning.chunk_id,
            role=ContextRole.SUPPORTING_CONTEXT,
            expansion_type=ContextExpansionType.PARENT_HEADING,
            content=heading,
        )
    ]


def fetch_adjacent_chunks(
    winning: Candidate,
    *,
    provider: ContextChunkProvider,
    user: UserContext,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> list[ContextSegment]:
    references = [
        ("previous_chunk_id", ContextExpansionType.PREVIOUS_CHUNK),
        ("next_chunk_id", ContextExpansionType.NEXT_CHUNK),
    ]
    requested = [
        value
        for key, _expansion_type in references
        if isinstance((value := winning.metadata.get(key)), str) and value.strip()
    ]
    records = provider.get_context_chunks(requested) if requested else {}
    segments: list[ContextSegment] = []
    for key, expansion_type in references:
        chunk_id = winning.metadata.get(key)
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            continue
        candidate = _authorized_support(
            records.get(chunk_id),
            winning=winning,
            user=user,
            as_of=as_of,
            include_historical=include_historical,
        )
        if candidate is not None:
            segments.append(
                _segment(
                    candidate,
                    winning_chunk_id=winning.chunk_id,
                    role=ContextRole.SUPPORTING_CONTEXT,
                    expansion_type=expansion_type,
                )
            )
    return segments


def fetch_referenced_definitions(
    winning: Candidate,
    *,
    provider: ContextChunkProvider,
    user: UserContext,
    max_definitions: int = 3,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> list[ContextSegment]:
    if max_definitions < 0:
        raise ValueError("max_definitions must not be negative.")
    raw_ids = winning.metadata.get("referenced_definition_chunk_ids", [])
    if not isinstance(raw_ids, list):
        return []
    chunk_ids = list(
        dict.fromkeys(
            item.strip()
            for item in raw_ids
            if isinstance(item, str) and item.strip()
        )
    )[:max_definitions]
    records = provider.get_context_chunks(chunk_ids) if chunk_ids else {}
    segments: list[ContextSegment] = []
    for chunk_id in chunk_ids:
        candidate = _authorized_support(
            records.get(chunk_id),
            winning=winning,
            user=user,
            as_of=as_of,
            include_historical=include_historical,
        )
        if candidate is not None:
            segments.append(
                _segment(
                    candidate,
                    winning_chunk_id=winning.chunk_id,
                    role=ContextRole.SUPPORTING_CONTEXT,
                    expansion_type=ContextExpansionType.REFERENCED_DEFINITION,
                )
            )
    return segments


def enforce_context_token_budget(
    segments: Sequence[ContextSegment],
    *,
    token_budget: int,
    token_counter: TokenCounter = _default_token_counter,
) -> tuple[list[ContextSegment], int, bool]:
    if token_budget < 1:
        raise ValueError("token_budget must be positive.")
    selected: list[ContextSegment] = []
    used = 0
    truncated = False
    for segment in segments:
        count = token_counter(segment.content)
        if count < 0:
            raise ValueError("token_counter must not return a negative count.")
        remaining = token_budget - used
        if count <= remaining:
            selected.append(segment)
            used += count
            continue
        truncated = True
        if remaining <= 0:
            break
        matches = list(re.finditer(r"\S+", segment.content, flags=re.UNICODE))
        if token_counter is not _default_token_counter or not matches:
            break
        clipped = segment.content[: matches[min(remaining, len(matches)) - 1].end()]
        selected.append(segment.model_copy(update={"content": clipped}))
        used += token_counter(clipped)
        break
    return selected, used, truncated


def _citation(segment: ContextSegment) -> Citation:
    metadata = segment.metadata
    document_number = str(metadata.get("document_number") or segment.document_id)
    title = str(metadata.get("title") or document_number)
    locator = str(metadata.get("section") or metadata.get("article") or "").strip()
    source = ", ".join(part for part in [document_number, locator] if part)
    return Citation(
        chunk_id=segment.chunk_id,
        document_id=segment.document_id,
        version_id=segment.version_id,
        document_number=document_number,
        title=title,
        source=source,
        article=metadata.get("article"),
        clause=metadata.get("clause"),
        point=metadata.get("point"),
        section=metadata.get("section"),
        page=metadata.get("page"),
        source_url=metadata.get("source_url"),
        excerpt=segment.content,
        citation_kind=(
            CitationKind.WINNING
            if segment.context_role == ContextRole.WINNING
            else CitationKind.EXPANDED
        ),
        winning_chunk_id=segment.winning_chunk_id,
        rerank_score=(
            min(max(float(metadata["rerank_score"]), 0.0), 1.0)
            if metadata.get("rerank_score") is not None
            else None
        ),
    )


def build_context_window(
    winning_candidates: Sequence[Candidate],
    *,
    provider: ContextChunkProvider,
    user: UserContext,
    token_budget: int,
    max_referenced_definitions: int = 3,
    token_counter: TokenCounter = _default_token_counter,
    as_of: date | datetime | None = None,
    include_historical: bool = False,
) -> ContextWindow:
    if len(winning_candidates) > 5:
        raise ValueError("Context expansion accepts at most five winning chunks.")
    segments: list[ContextSegment] = []
    for winning in winning_candidates:
        segments.append(_winning_segment(winning))
        segments.extend(
            expand_parent_context(
                winning,
                provider=provider,
                user=user,
                as_of=as_of,
                include_historical=include_historical,
            )
        )
        segments.extend(
            fetch_referenced_definitions(
                winning,
                provider=provider,
                user=user,
                max_definitions=max_referenced_definitions,
                as_of=as_of,
                include_historical=include_historical,
            )
        )
        segments.extend(
            fetch_adjacent_chunks(
                winning,
                provider=provider,
                user=user,
                as_of=as_of,
                include_historical=include_historical,
            )
        )

    unique: list[ContextSegment] = []
    seen: set[tuple[str, ContextExpansionType, str]] = set()
    for segment in segments:
        key = (segment.chunk_id, segment.expansion_type, segment.winning_chunk_id)
        if key not in seen:
            seen.add(key)
            unique.append(segment)
    budgeted, token_count, truncated = enforce_context_token_budget(
        unique,
        token_budget=token_budget,
        token_counter=token_counter,
    )
    warnings = ["Context was truncated to the configured token budget."] if truncated else []
    return ContextWindow(
        segments=budgeted,
        citations=[_citation(segment) for segment in budgeted],
        token_count=token_count,
        token_budget=token_budget,
        truncated=truncated,
        warnings=warnings,
    )
