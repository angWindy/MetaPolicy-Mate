"""Bounded, access-filtered conversation memory for follow-up RAG questions."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from src.domain.entities.chat_turn import ChatTurn

_FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:còn|thế\s*còn|vậy|nó|họ|người\s*này|mức\s*này|"
    r"điều\s*đó|văn\s*bản\s*đó|trường\s*hợp\s*này|như\s*trên|"
    r"vừa\s*nêu|câu\s*trước|tiếp\s*theo)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ConversationMemory:
    retrieval_query: str
    prompt_context: str
    context_dependent: bool


def is_context_dependent_follow_up(message: str) -> bool:
    """Return whether the current question explicitly refers to prior turns."""

    return bool(_FOLLOW_UP_PATTERN.search(message.strip()))


def _citation_document_numbers(turn: ChatTurn) -> list[str]:
    return list(
        dict.fromkeys(
            str(citation.get("document_number") or "").strip()
            for citation in turn.citations
            if isinstance(citation, dict)
            and str(citation.get("document_number") or "").strip()
        )
    )


def build_conversation_memory(
    message: str,
    turns: Sequence[ChatTurn],
    *,
    max_turns: int = 4,
    max_chars: int = 2400,
) -> ConversationMemory:
    """Build separate retrieval and generation views of safe session history.

    The caller must pass only turns whose citations remain accessible. Retrieval
    receives the last user topic and document identities only for an explicit
    follow-up. The answer generator receives bounded history, clearly marked as
    conversational context rather than factual evidence.
    """

    current = message.strip()
    selected = list(turns[-max_turns:]) if max_turns > 0 else []
    if not selected:
        return ConversationMemory(
            retrieval_query=current,
            prompt_context="",
            context_dependent=False,
        )

    context_lines: list[str] = []
    for index, turn in enumerate(selected, start=1):
        context_lines.append(f"Turn {index} user: {turn.question.strip()}")
        document_numbers = _citation_document_numbers(turn)
        if document_numbers:
            context_lines.append(
                f"Turn {index} cited documents: {', '.join(document_numbers)}"
            )
            context_lines.append(
                f"Turn {index} assistant: {turn.answer.strip()}"
            )
    prompt_context = "\n".join(context_lines)
    if len(prompt_context) > max_chars:
        prompt_context = prompt_context[-max_chars:]

    context_dependent = is_context_dependent_follow_up(current)
    if not context_dependent:
        retrieval_query = current
    else:
        previous = selected[-1]
        document_numbers = _citation_document_numbers(previous)
        retrieval_parts = [
            current,
            f"Previous user topic: {previous.question.strip()}",
        ]
        if document_numbers:
            retrieval_parts.append(
                f"Previously cited documents: {', '.join(document_numbers)}"
            )
        retrieval_query = "\n".join(retrieval_parts)

    return ConversationMemory(
        retrieval_query=retrieval_query,
        prompt_context=prompt_context,
        context_dependent=context_dependent,
    )
