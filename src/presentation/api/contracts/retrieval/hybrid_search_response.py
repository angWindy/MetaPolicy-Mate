from pydantic import BaseModel


class HybridSearchItemResponse(
    BaseModel
):
    chunk_id: str

    text: str

    score: float

    source: str

    metadata: dict


class HybridSearchResponse(
    BaseModel
):
    query: str

    has_evidence: bool

    items: list[
        HybridSearchItemResponse
    ]