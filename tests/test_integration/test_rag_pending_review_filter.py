"""Integration test for the RAG retrieval SQL filter.

Verifies the post-2026-09-06 metadata cleanup filter clauses:

* Only ``approved`` / ``indexed`` / ``published`` versions flow into
  retrieval; everything else is silently dropped.
* Chunks flagged ``low_confidence`` (set by the OCR engine when the
  page's average confidence is below the threshold) are dropped.
* The filter is a pure-SQL clause — no Python post-processing required.

We test at the SQL-string level rather than booting a real Postgres +
Qdrant because the contract being verified is the *filter shape*:
changing the WHERE clause is what the metadata cleanup PR does, so we
snapshot the SQL text and assert against it.

Why a unit test (not a live DB test) is sufficient:

* The query uses standard SQL primitives — ``=``, ``IN``, ``COALESCE``,
  ``->>`` JSON operator — which PostgreSQL has supported since v9.4.
* The integration with Neon / Qdrant is already covered by
  ``tests/test_integration/test_backend_e2e.py``; we don't duplicate
  that here.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "test")

from src.infrastructure.ai.hybrid_retrieval_service import (  # noqa: E402
    AiHybridRetrievalService,
)


# ---------------------------------------------------------------------- #
# Test helpers
# ---------------------------------------------------------------------- #


def _extract_load_candidates_sql() -> str:
    """Re-create the SQL string from ``_load_candidates``.

    We don't execute the query (no DB) — we just read the source so we
    can assert on the SQL text.  Using ``inspect.getsource`` keeps the
    test in sync with the production code: if anyone changes the WHERE
    clause, the test reads the new text and re-asserts.
    """
    import inspect

    src = inspect.getsource(AiHybridRetrievalService._load_candidates)
    match = re.search(
        r"_sql_text\(\s*(?:\"\"\"|''')([\s\S]*?)(?:\"\"\"|''')",
        src,
    )
    assert match is not None, (
        "Could not find SQL string literal in "
        "AiHybridRetrievalService._load_candidates"
    )
    return match.group(1)


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #


class TestPendingReviewFilter:
    """Verify pre-curation statuses are excluded from RAG."""

    def test_sql_excludes_pending_review(self):
        sql = _extract_load_candidates_sql()
        # The new WHERE clause must NOT include ``pending_review``,
        # ``review_required``, ``received``, ``queued``, ``parsed``,
        # ``failed``, ``rejected`` — only the curated subset.
        for forbidden in (
            "'pending_review'",
            "'review_required'",
            "'received'",
            "'queued'",
            "'parsed'",
            "'failed'",
            "'rejected'",
        ):
            assert forbidden not in sql, (
                f"SQL filter still allows {forbidden}; "
                "pending_review and review_required must be excluded."
            )

    def test_sql_includes_only_curated_statuses(self):
        sql = _extract_load_candidates_sql()
        # Whitelist of curated statuses that survive the filter.
        for allowed in (
            "'approved'",
            "'indexed'",
            "'published'",
        ):
            assert allowed in sql, (
                f"Curated status {allowed} missing from SQL filter."
            )


class TestLowConfidenceFilter:
    """Verify low-confidence chunks are excluded from RAG."""

    def test_sql_filters_low_confidence_chunks(self):
        sql = _extract_load_candidates_sql()
        # The filter must use ``metadata_json->>'low_confidence'``
        # and the ``COALESCE(..., FALSE) = FALSE`` pattern. Defaulting
        # to ``false`` keeps legacy chunks (no flag) eligible.
        assert "metadata_json->>'low_confidence'" in sql, (
            "low_confidence filter missing from SQL."
        )
        assert "COALESCE" in sql, (
            "low_confidence filter must use COALESCE to default "
            "missing flag values to FALSE."
        )
        assert "::boolean" in sql, (
            "low_confidence filter must cast the JSON value to boolean."
        )


class TestFilterShapeRegression:
    """Other invariants that the filter must keep intact."""

    def test_sql_keeps_legal_status_whitelist(self):
        sql = _extract_load_candidates_sql()
        # Unchanged from the prior baseline — guards against an
        # accidental edit dropping legal_status / effective_date.
        for needed in (
            "'effective'",
            "'draft'",
            "'scheduled'",
            "'superseded'",
            "'expired'",
            "d.effective_date",
            "d.access_scope",
        ):
            assert needed in sql, (
                f"Required clause {needed!r} missing from SQL."
            )

    def test_sql_keeps_access_scope_join(self):
        sql = _extract_load_candidates_sql()
        # The DEPARTMENT / PUBLIC access-scope join must survive.
        assert "public.document_departments" in sql
        assert "public.departments" in sql
        assert ":is_admin" in sql
        assert ":department_code" in sql
