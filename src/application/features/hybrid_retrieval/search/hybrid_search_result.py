from dataclasses import dataclass


@dataclass(frozen=True)
class HybridSearchItemDto:
    chunk_id: str

    text: str

    score: float

    source: str

    metadata: dict


@dataclass(frozen=True)
class HybridSearchResult:
    query: str

    items: list[
        HybridSearchItemDto
    ]

    has_evidence: bool