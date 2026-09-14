from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ExtractedSectionMetadata:
    metadata: dict

    cross_references: list[dict]

    needs_human_review: bool

    rationale: str | None


class SectionMetadataExtractionService(
    Protocol
):
    async def extract(
        self,
        *,
        filename: str,
        text: str,
        base_metadata: dict,
    ) -> ExtractedSectionMetadata:
        ...