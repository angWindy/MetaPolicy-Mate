from __future__ import annotations

from scripts.audit_rag_index_alignment import compare_index


def _expected(chunk_id: str, content_hash: str) -> dict:
    return {
        "id": chunk_id,
        "embedding_text": "content",
        "payload": {"content_hash": content_hash},
    }


def _payload(chunk_id: str, content_hash: str) -> dict:
    return {
        "tenant_id": "hust",
        "document_id": "doc-1",
        "version_id": "version-1",
        "chunk_id": chunk_id,
        "classification": "public",
        "status": "published",
        "content_hash": content_hash,
        "embedding_model": "text-embedding-3-small",
        "embedding_version": "1",
        "index_version": "p234_qdrant",
    }


def test_compare_index_reports_missing_stale_invalid_and_hash_mismatch() -> None:
    expected = [_expected("a", "hash-a"), _expected("b", "hash-b")]
    actual = {
        "a": _payload("a", "wrong-hash"),
        "stale": {"chunk_id": "stale"},
    }

    report = compare_index(expected, actual, "p234_qdrant")

    assert report.aligned is False
    assert report.missing_ids == ("b",)
    assert report.stale_ids == ("stale",)
    assert report.invalid_payload_ids == ()
    assert report.content_hash_mismatch_ids == ("a",)


def test_compare_index_accepts_canonical_equal_payload() -> None:
    expected = [_expected("a", "hash-a")]

    report = compare_index(
        expected,
        {"a": _payload("a", "hash-a")},
        "p234_qdrant",
    )

    assert report.aligned is True
