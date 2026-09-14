from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractedCrossReference:
    document_number: str

    confidence: float

    context_text: str | None


@dataclass(frozen=True)
class ExtractedDocumentMetadata:
    document_number: str | None

    document_number_confidence: float

    title: str | None

    title_confidence: float

    needs_human_review: bool

    rationale: str

    raw_header_text: str

    cross_references: list[
        ExtractedCrossReference
    ]


class DocumentMetadataExtractionService(
    Protocol
):
    async def extract(
        self,
        *,
        filename: str,
        sections: list[str],
    ) -> ExtractedDocumentMetadata:
        ...