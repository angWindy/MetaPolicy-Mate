"""Multi-intent decomposition for the retrieval workflow.

When the intent classifier flags MULTI_INTENT, the workflow
decomposes the user query into atomic sub-queries (split on "?", ";",
or multi-intent connectors) and runs the standard retrieval subgraph
sequentially for each sub-query. The merged result carries the
concatenated answer, de-duplicated citations, and the worst-case
confidence across sub-answers.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.rag.workflow import RetrievalState

# Same connector vocabulary that ``query_transform._is_multi_intent``
# uses to recognise multi-intent queries. We split on these only AFTER
# the question marks / semicolons are exhausted.
_CONNECTOR_PATTERN = re.compile(
    r"\s+(?:và|đồng thời|ngoài ra)\s+",
    flags=re.IGNORECASE | re.UNICODE,
)
_QUESTION_RE = re.compile(r"\?+", flags=re.UNICODE)


def _split_intents(query: str) -> list[str]:
    """Split a multi-intent query into atomic sub-queries."""

    if not isinstance(query, str) or not query.strip():
        return [query]
    text = query.strip()
    # Split on question marks first ("…? …? …?")
    parts = _QUESTION_RE.split(text)
    parts = [part.strip(" ,;\n\t") for part in parts if part.strip(" ,;\n\t")]
    if len(parts) <= 1:
        # Fall back to semicolon split.
        parts = [p.strip() for p in text.split(";") if p.strip()]
    if len(parts) <= 1:
        # Fall back to multi-intent connectors ("áp dụng cho HUST và HUCE").
        parts = [
            segment.strip()
            for segment in _CONNECTOR_PATTERN.split(text)
            if segment.strip()
        ]
    if not parts:
        return [text]
    return parts


def _merge_answers(answers: list[str]) -> str:
    return "\n\n".join(answer for answer in answers if answer and answer.strip())


def _dedupe_citations(citation_lists: list[list[Any]]) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for group in citation_lists:
        for citation in group:
            chunk_id = getattr(citation, "chunk_id", None)
            if isinstance(chunk_id, str):
                if chunk_id in seen:
                    continue
                seen.add(chunk_id)
            merged.append(citation)
    return merged


_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}


def _aggregate_confidence(confidences: list[str]) -> str:
    if not confidences:
        return "low"
    ranked = sorted(
        confidences,
        key=lambda value: _CONFIDENCE_RANK.get(value.lower(), 0),
    )
    return ranked[0]


async def _run_subgraph(
    subgraph: Any,
    state: "RetrievalState",
    sub_query: str,
) -> "RetrievalState":
    """Invoke the workflow subgraph for a single sub-query."""

    # Lazy import to avoid a circular dependency with ``workflow``.
    from src.rag.workflow import _visit  # noqa: F401  (kept for future use)

    sub_state: "RetrievalState" = {
        **state,
        "original_query": sub_query,
        "query": sub_query,
        "visited": [],
        # Reset per-attempt bookkeeping so retries / multi-intent don't
        # leak counters across sub-queries.
        "attempts": 0,
        "max_attempts": min(state.get("max_attempts", 2) or 2, 2),
    }
    config = subgraph._config(  # noqa: SLF001 - workflow-owned helper
        state.get("thread_id") or "decompose"
    )
    if not subgraph._runtime_inputs.get(config["configurable"]["thread_id"]):  # noqa: SLF001
        subgraph._runtime_inputs[config["configurable"]["thread_id"]] = sub_state  # noqa: SLF001
    return await subgraph.graph.ainvoke(sub_state, config)


async def decompose_query_node(
    state: "RetrievalState",
    subgraph: Any | None = None,
) -> dict[str, Any]:
    """Decompose a multi-intent query into atomic sub-queries.

    Parameters
    ----------
    state:
        Current retrieval state. Must contain ``original_query`` and
        ``user`` for downstream subgraphs to operate.
    subgraph:
        The compiled ``RetrievalWorkflow`` instance. The default wiring
        in ``workflow._route_after_intent`` passes ``self`` so the
        decompose node re-enters the same workflow.
    """

    # Lazy import to avoid a circular dependency with ``workflow``.
    from src.rag.workflow import _visit

    original = (state.get("original_query") or state.get("query") or "").strip()
    sub_queries = _split_intents(original)

    if len(sub_queries) <= 1 or subgraph is None:
        # Not actually multi-intent or no subgraph wired in — fall back
        # to letting the workflow continue normally so existing
        # multi-intent handling in transform_query still applies.
        return {
            "transformed_queries": sub_queries,
            "visited": _visit(state, "decompose_query_node"),
        }

    sub_results: list[RetrievalState] = await asyncio.gather(
        *(
            _run_subgraph(subgraph, state, sub_query)
            for sub_query in sub_queries
        ),
        return_exceptions=False,
    )

    answers = [str(result.get("answer", "")) for result in sub_results]
    citation_lists = [list(result.get("citations", []) or []) for result in sub_results]
    confidences = [str(result.get("confidence", "low")) for result in sub_results]

    return {
        "answer": _merge_answers(answers),
        "citations": _dedupe_citations(citation_lists),
        "cited_chunk_ids": list(
            dict.fromkeys(
                chunk_id
                for citations in citation_lists
                for citation in citations
                for chunk_id in [getattr(citation, "chunk_id", None)]
                if isinstance(chunk_id, str)
            )
        ),
        "confidence": _aggregate_confidence(confidences),
        "warnings": [],
        "outcome": "multi_intent_response",
        "transformed_queries": sub_queries,
        "visited": _visit(state, "decompose_query_node"),
    }


__all__ = ["decompose_query_node", "_split_intents"]
