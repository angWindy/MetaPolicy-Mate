from dataclasses import dataclass

from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)


@dataclass(frozen=True)
class GetRegulatoryDocumentsResult:
    items: list[
        RegulatoryDocumentItem
    ]

    total: int
    page: int
    page_size: int