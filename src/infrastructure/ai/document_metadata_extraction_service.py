from dataclasses import dataclass

from src.application.common.interfaces.document_metadata_extraction_service import (
    DocumentMetadataExtractionService,
    ExtractedCrossReference,
    ExtractedDocumentMetadata,
)
from src.ingestion.document_number import (
    extract_document_number,
)
from src.ingestion.metadata_extractor import (
    extract_metadata,
)


@dataclass(frozen=True)
class _TextBlock:
    text: str


class AiDocumentMetadataExtractionService(
    DocumentMetadataExtractionService
):
    async def extract(
        self,
        *,
        filename: str,
        sections: list[str],
    ) -> ExtractedDocumentMetadata:
        blocks = [
            _TextBlock(
                text=text
            )
            for text in sections
            if text
        ]

        result = extract_metadata(
            blocks,
            filename_hint=filename,
        )

        title = (
            result.title.title
            if result.title
            else None
        )

        title_confidence = (
            result.title.confidence
            if result.title
            else 0.0
        )

        full_text = "\n\n".join(
            sections
        )

        references = (
            self._extract_cross_references(
                full_text=full_text,
                own_document_number=(
                    result.document_number
                ),
            )
        )

        return ExtractedDocumentMetadata(
            document_number=(
                result.document_number
            ),

            document_number_confidence=(
                result
                .document_number_confidence
            ),

            title=title,

            title_confidence=(
                title_confidence
            ),

            needs_human_review=(
                result.needs_human_review
            ),

            rationale=(
                result.rationale
            ),

            raw_header_text=(
                result.raw_header_text
            ),

            cross_references=(
                references
            ),
        )

    @staticmethod
    def _extract_cross_references(
        *,
        full_text: str,
        own_document_number: (
            str | None
        ),
    ) -> list[
        ExtractedCrossReference
    ]:
        probe = extract_document_number(
            full_text
        )

        seen: set[str] = set()

        results: list[
            ExtractedCrossReference
        ] = []

        for candidate in (
            probe.candidates
        ):
            normalized = (
                candidate.strip()
            )

            if not normalized:
                continue

            if (
                own_document_number
                and normalized.lower()
                == own_document_number
                .strip()
                .lower()
            ):
                continue

            key = normalized.lower()

            if key in seen:
                continue

            seen.add(key)

            context = (
                AiDocumentMetadataExtractionService
                ._find_context(
                    full_text,
                    normalized,
                )
            )

            results.append(
                ExtractedCrossReference(
                    document_number=(
                        normalized
                    ),

                    confidence=(
                        probe.confidence
                    ),

                    context_text=context,
                )
            )

        return results

    @staticmethod
    def _find_context(
        text: str,
        value: str,
    ) -> str | None:
        index = text.lower().find(
            value.lower()
        )

        if index < 0:
            return None

        start = max(
            0,
            index - 160,
        )

        end = min(
            len(text),
            index + len(value) + 160,
        )

        return text[
            start:end
        ].strip()