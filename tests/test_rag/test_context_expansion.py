from __future__ import annotations

from datetime import UTC, datetime

from src.domain.schemas import (
    Candidate,
    CitationKind,
    ContextExpansionType,
    ContextRole,
    QdrantPayload,
    UserContext,
)
from src.retrieval.context_expansion import (
    AuthoritativeChunk,
    build_context_window,
    expand_parent_context,
    fetch_adjacent_chunks,
    fetch_referenced_definitions,
)

AS_OF = datetime(2026, 8, 4, tzinfo=UTC)


def make_candidate(
    chunk_id: str,
    *,
    document_id: str = "doc-1",
    version_id: str = "version-current",
    content: str | None = None,
    metadata: dict | None = None,
) -> Candidate:
    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=version_id,
        content=content or f"Nội dung {chunk_id}",
        metadata={
            "title": "Quy định nghỉ phép",
            "document_number": "01/QĐ-ĐHBK",
            "section": "Điều 5",
            **(metadata or {}),
        },
        dense_rank=1,
        sparse_rank=1,
        fusion_score=0.1,
        rerank_score=4.2,
    )


def make_payload(candidate: Candidate, **overrides) -> QdrantPayload:
    values = {
        "tenant_id": "hust",
        "document_id": candidate.document_id,
        "version_id": candidate.version_id,
        "chunk_id": candidate.chunk_id,
        "parent_chunk_id": None,
        "previous_chunk_id": None,
        "next_chunk_id": None,
        "owner_unit": "TCCB",
        "allowed_roles": ["staff"],
        "allowed_units": ["TCCB"],
        "classification": "internal",
        "status": "published",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "page": 3,
        "section": "Điều 5",
        "content_hash": f"sha256:{candidate.chunk_id}",
        "embedding_model": "test-dense",
        "embedding_version": "1",
        "sparse_model": "test-sparse",
        "sparse_version": "1",
        "index_version": "index-current",
    }
    values.update(overrides)
    return QdrantPayload.model_validate(values)


class FakePostgresProvider:
    def __init__(self, candidates: list[Candidate]) -> None:
        self.records = {
            candidate.chunk_id: AuthoritativeChunk(
                candidate=candidate,
                access_payload=make_payload(candidate),
            )
            for candidate in candidates
        }
        self.requests: list[list[str]] = []

    def get_context_chunks(self, chunk_ids):
        self.requests.append(list(chunk_ids))
        return {
            chunk_id: self.records[chunk_id]
            for chunk_id in chunk_ids
            if chunk_id in self.records
        }


def make_user() -> UserContext:
    return UserContext(
        user_id="user-1",
        tenant_id="hust",
        department="TCCB",
        roles={"staff"},
        clearance_level="internal",
    )


def test_parent_heading_preserves_title_and_article_without_fetching_document():
    winning = make_candidate(
        "winner",
        metadata={"heading_path": ["Chương II", "Điều 5. Nghỉ phép"]},
    )
    provider = FakePostgresProvider([])

    segments = expand_parent_context(
        winning,
        provider=provider,
        user=make_user(),
        as_of=AS_OF,
    )

    assert len(segments) == 1
    assert segments[0].expansion_type == ContextExpansionType.PARENT_HEADING
    assert "Quy định nghỉ phép" in segments[0].content
    assert "Điều 5. Nghỉ phép" in segments[0].content
    assert segments[0].context_role == ContextRole.SUPPORTING_CONTEXT
    assert segments[0].metadata["supporting_context"] is True
    assert provider.requests == []


def test_fetches_only_previous_and_next_from_same_document_version():
    previous = make_candidate("previous")
    following = make_candidate("next")
    winning = make_candidate(
        "winner",
        metadata={"previous_chunk_id": "previous", "next_chunk_id": "next"},
    )
    provider = FakePostgresProvider([previous, following])

    segments = fetch_adjacent_chunks(
        winning,
        provider=provider,
        user=make_user(),
        as_of=AS_OF,
    )

    assert [segment.chunk_id for segment in segments] == ["previous", "next"]
    assert [segment.expansion_type for segment in segments] == [
        ContextExpansionType.PREVIOUS_CHUNK,
        ContextExpansionType.NEXT_CHUNK,
    ]
    assert provider.requests == [["previous", "next"]]


def test_cross_version_adjacent_chunk_is_blocked():
    old = make_candidate("old-next", version_id="version-old")
    winning = make_candidate("winner", metadata={"next_chunk_id": "old-next"})
    provider = FakePostgresProvider([old])

    segments = fetch_adjacent_chunks(
        winning,
        provider=provider,
        user=make_user(),
        as_of=AS_OF,
    )

    assert segments == []


def test_unauthorized_adjacent_chunk_is_blocked_by_policy_recheck():
    adjacent = make_candidate("restricted-next")
    winning = make_candidate(
        "winner",
        metadata={"next_chunk_id": "restricted-next"},
    )
    provider = FakePostgresProvider([adjacent])
    provider.records[adjacent.chunk_id] = AuthoritativeChunk(
        candidate=adjacent,
        access_payload=make_payload(
            adjacent,
            allowed_roles=["manager"],
            allowed_units=["LEGAL"],
        ),
    )

    segments = fetch_adjacent_chunks(
        winning,
        provider=provider,
        user=make_user(),
        as_of=AS_OF,
    )

    assert segments == []


def test_referenced_definition_is_checked_and_marked_as_supporting():
    definition = make_candidate(
        "definition",
        content="Nghỉ phép là thời gian nghỉ được phê duyệt.",
    )
    winning = make_candidate(
        "winner",
        metadata={"referenced_definition_chunk_ids": ["definition"]},
    )
    provider = FakePostgresProvider([definition])

    segments = fetch_referenced_definitions(
        winning,
        provider=provider,
        user=make_user(),
        as_of=AS_OF,
    )

    assert [segment.chunk_id for segment in segments] == ["definition"]
    assert segments[0].expansion_type == ContextExpansionType.REFERENCED_DEFINITION
    assert segments[0].metadata["winning_chunk_id"] == "winner"


def test_context_window_enforces_budget_and_distinguishes_citations():
    adjacent = make_candidate(
        "next",
        content="Đoạn kế tiếp có nhiều nội dung hỗ trợ cho bằng chứng chính.",
    )
    winning = make_candidate(
        "winner",
        content="Cán bộ được nghỉ phép theo kế hoạch đã phê duyệt.",
        metadata={
            "heading_path": ["Chương II", "Điều 5. Nghỉ phép"],
            "next_chunk_id": "next",
        },
    )
    provider = FakePostgresProvider([adjacent])

    window = build_context_window(
        [winning],
        provider=provider,
        user=make_user(),
        token_budget=12,
        as_of=AS_OF,
    )

    assert window.token_count <= 12
    assert window.truncated is True
    assert window.warnings
    assert "Quy định nghỉ phép" in window.segments[0].content
    assert window.citations[0].citation_kind == CitationKind.WINNING
    assert all(
        citation.citation_kind == CitationKind.EXPANDED
        for citation in window.citations[1:]
    )
    assert all(
        citation.winning_chunk_id == "winner" for citation in window.citations
    )
