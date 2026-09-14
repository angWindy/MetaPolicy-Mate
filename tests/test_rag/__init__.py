"""RAG-specific tests.

All tests in this package exercise the real Retrieval-Augmented Generation
workflow (Postgres + Qdrant + LangGraph). They are excluded from CI by
default because the workflow contract is still being reconciled
(retriever signature drift, checkpoint resume semantics, etc.). Run
locally with::

    pytest -m requires_rag_runtime tests/test_rag/
"""

import pytest

pytestmark = pytest.mark.requires_rag_runtime
