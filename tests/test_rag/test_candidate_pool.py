from __future__ import annotations

from typing import Any

import pytest

from src.domain.schemas import Candidate
from src.rag.config import RAGSettings
from src.retrieval.candidate_pool import (
    calculate_candidate_diversity,
    cap_chunks_per_document,
    clean_candidate_pool,
    preserve_definition_chunks,
    remove_exact_duplicates,
    remove_near_duplicates,
)


def make_candidate(
    chunk_id: str,
    content: str,
    *,
    document_id: str = "doc-1",
    content_hash: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Candidate:
    payload = dict(metadata or {})
    if content_hash is not None:
        payload["content_hash"] = content_hash
    return Candidate(
        chunk_id=chunk_id,
        document_id=document_id,
        version_id=f"version-{document_id}",
        content=content,
        metadata=payload,
        dense_rank=1,
        sparse_rank=None,
        fusion_score=1.0,
        rerank_score=None,
    )


def test_remove_exact_duplicates_uses_chunk_id_then_content_hash():
    original = make_candidate("chunk-a", "Nội dung A", content_hash="sha256:a")
    duplicate_id = original.model_copy(update={"fusion_score": 0.5})
    copied_content = make_candidate(
        "chunk-copy", "Nội dung A", content_hash="sha256:a"
    )
    unique = make_candidate("chunk-b", "Nội dung B", content_hash="sha256:b")

    result = remove_exact_duplicates(
        [original, duplicate_id, copied_content, unique]
    )

    assert [candidate.chunk_id for candidate in result] == ["chunk-a", "chunk-b"]
    assert result[0].metadata["exact_duplicate_chunk_ids"] == ["chunk-copy"]


def test_exact_dedupe_prefers_definition_copy():
    ordinary = make_candidate(
        "ordinary", "Học phí là khoản phải nộp.", content_hash="sha256:same"
    )
    definition = make_candidate(
        "definition",
        "Học phí là khoản phải nộp.",
        content_hash="sha256:same",
        metadata={"chunk_type": "definition"},
    )
    result = remove_exact_duplicates([ordinary, definition])
    assert [candidate.chunk_id for candidate in result] == ["definition"]
    assert result[0].metadata["exact_duplicate_chunk_ids"] == ["ordinary"]


def test_remove_near_duplicates_is_conservative_across_documents():
    content = "Sinh viên nộp hồ sơ tại Phòng Công tác Sinh viên trước ngày 30 tháng 6."
    original = make_candidate("original", content, content_hash="sha256:1")
    overlapping = make_candidate(
        "overlap",
        content.upper(),
        content_hash="sha256:2",
    )
    another_document = make_candidate(
        "other-document",
        content.lower(),
        document_id="doc-2",
        content_hash="sha256:3",
    )

    result = remove_near_duplicates(
        [original, overlapping, another_document],
        similarity_threshold=0.95,
    )

    assert [candidate.chunk_id for candidate in result] == [
        "original",
        "other-document",
    ]


def test_near_dedupe_keeps_different_articles_and_clauses_in_same_document():
    content = "Sinh viên được miễn học phí khi đáp ứng đầy đủ các điều kiện."
    article_one = make_candidate(
        "article-1",
        content,
        content_hash="sha256:article-1",
        metadata={"article": "1", "clause": "1", "section": "Điều 1"},
    )
    article_two = make_candidate(
        "article-2",
        content.upper(),
        content_hash="sha256:article-2",
        metadata={"article": "2", "clause": "1", "section": "Điều 2"},
    )

    result = remove_near_duplicates([article_one, article_two])

    assert [candidate.chunk_id for candidate in result] == [
        "article-1",
        "article-2",
    ]


def test_definition_chunk_replaces_near_duplicate_ordinary_chunk():
    content = "Học phí là khoản tiền người học phải nộp theo quy định."
    ordinary = make_candidate(
        "ordinary", content, content_hash="sha256:ordinary"
    )
    definition = make_candidate(
        "definition",
        content.upper(),
        content_hash="sha256:definition",
        metadata={"section": "Giải thích từ ngữ"},
    )

    result = remove_near_duplicates([ordinary, definition])

    assert [candidate.chunk_id for candidate in result] == ["definition"]
    assert preserve_definition_chunks(result) == [definition]


def test_cap_four_chunks_per_document_preserves_definition():
    candidates = [
        make_candidate(
            f"regular-{index}",
            f"Nội dung riêng biệt số {index}",
            content_hash=f"sha256:regular-{index}",
        )
        for index in range(1, 5)
    ]
    definition = make_candidate(
        "definition",
        "Giải thích thuật ngữ học phí.",
        content_hash="sha256:definition",
        metadata={"is_definition": True},
    )

    result = cap_chunks_per_document(
        [*candidates, definition],
        limit=10,
        max_chunks_per_document=4,
    )

    assert len(result) == 4
    assert "definition" in {candidate.chunk_id for candidate in result}
    assert "regular-4" not in {candidate.chunk_id for candidate in result}


def test_calculate_candidate_diversity_before_and_after_cleaning():
    original = make_candidate("a", "Nội dung A", content_hash="sha256:a")
    duplicate = make_candidate("a-copy", "Nội dung A", content_hash="sha256:a")
    other = make_candidate(
        "b",
        "Nội dung B",
        document_id="doc-2",
        content_hash="sha256:b",
    )
    before = calculate_candidate_diversity([original, duplicate, other])
    after = calculate_candidate_diversity(
        remove_exact_duplicates([original, duplicate, other])
    )

    assert before.candidate_count == 3
    assert before.unique_content_ratio == pytest.approx(2 / 3)
    assert after.candidate_count == 2
    assert after.unique_chunk_ratio == 1.0
    assert after.unique_content_ratio == 1.0
    assert after.document_diversity_ratio == 1.0


def test_candidate_pool_baseline_has_zero_recall_loss():
    relevant = {"policy", "procedure", "definition"}
    policy = make_candidate(
        "policy",
        "Điều kiện miễn học phí áp dụng cho sinh viên thuộc diện chính sách.",
        document_id="doc-policy",
        content_hash="sha256:policy",
        metadata={"article": "5"},
    )
    procedure = make_candidate(
        "procedure",
        "Hồ sơ được nộp tại Phòng Công tác Sinh viên trước ngày 30 tháng 6.",
        document_id="doc-procedure",
        content_hash="sha256:procedure",
    )
    definition = make_candidate(
        "definition",
        "Học phí là khoản tiền người học phải nộp theo quy định.",
        document_id="doc-definition",
        content_hash="sha256:definition",
        metadata={"chunk_type": "definition"},
    )
    pool = [
        policy,
        policy,
        make_candidate(
            "policy-copy",
            policy.content,
            document_id="doc-policy",
            content_hash="sha256:policy",
        ),
        procedure,
        make_candidate(
            "procedure-overlap",
            procedure.content.upper(),
            document_id="doc-procedure",
            content_hash="sha256:procedure-overlap",
        ),
        definition,
        make_candidate(
            "noise-1",
            "Thông tin liên hệ tổng quát.",
            document_id="doc-noise-1",
            content_hash="sha256:noise-1",
        ),
        make_candidate(
            "noise-2",
            "Lịch làm việc của đơn vị.",
            document_id="doc-noise-2",
            content_hash="sha256:noise-2",
        ),
    ]

    cleaned = clean_candidate_pool(pool, limit=60)
    before_diversity = calculate_candidate_diversity(pool)
    after_diversity = calculate_candidate_diversity(cleaned)

    def recall(candidates: list[Candidate]) -> float:
        returned = {candidate.chunk_id for candidate in candidates}
        return len(returned & relevant) / len(relevant)

    before_recall = recall(pool)
    after_recall = recall(cleaned)
    assert len(pool) == 8
    assert len(cleaned) == 5
    assert before_recall == 1.0
    assert after_recall == 1.0
    assert before_recall - after_recall <= 0.05
    assert len({candidate.chunk_id for candidate in cleaned}) == len(cleaned)
    assert before_diversity.unique_chunk_ratio == pytest.approx(0.875)
    assert before_diversity.unique_content_ratio == pytest.approx(0.75)
    assert before_diversity.document_diversity_ratio == pytest.approx(0.625)
    assert before_diversity.max_chunks_per_document == 3
    assert after_diversity.unique_chunk_ratio == 1.0
    assert after_diversity.unique_content_ratio == 1.0
    assert after_diversity.document_diversity_ratio == 1.0
    assert after_diversity.max_chunks_per_document == 1


def test_near_duplicate_threshold_has_conservative_default_and_bounds():
    assert RAGSettings().near_duplicate_similarity_threshold == 0.95
    with pytest.raises(ValueError):
        RAGSettings(near_duplicate_similarity_threshold=0.79)
    with pytest.raises(ValueError):
        RAGSettings(near_duplicate_similarity_threshold=1.01)
