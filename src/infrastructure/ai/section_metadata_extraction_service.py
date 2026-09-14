from src.application.common.interfaces.document_metadata_extraction_service import (
    DocumentMetadataExtractionService,
)
from src.application.common.interfaces.section_metadata_extraction_service import (
    ExtractedSectionMetadata,
    SectionMetadataExtractionService,
)


class AiSectionMetadataExtractionService(
    SectionMetadataExtractionService
):
    def __init__(
        self,
        document_metadata_extraction_service: (
            DocumentMetadataExtractionService
        ),
    ) -> None:
        self._document_metadata_extraction_service = (
            document_metadata_extraction_service
        )

    async def extract(
        self,
        *,
        filename: str,
        text: str,
        base_metadata: dict,
    ) -> ExtractedSectionMetadata:
        result = await (
            self
            ._document_metadata_extraction_service
            .extract(
                filename=filename,
                sections=[text],
            )
        )

        metadata = dict(
            base_metadata or {}
        )

        metadata.update(
            {
                "document_number": (
                    result.document_number
                ),
                "document_number_confidence": (
                    result
                    .document_number_confidence
                ),
                "title": result.title,
                "title_confidence": (
                    result.title_confidence
                ),
                "raw_header_text": (
                    result.raw_header_text
                ),
            }
        )

        cross_references = [
            {
                "document_number": (
                    item.document_number
                ),
                "confidence": (
                    item.confidence
                ),
                "context_text": (
                    item.context_text
                ),
            }
            for item
            in result.cross_references
        ]

        return ExtractedSectionMetadata(
            metadata=metadata,
            cross_references=(
                cross_references
            ),
            needs_human_review=(
                result.needs_human_review
            ),
            rationale=(
                result.rationale
            ),
        )