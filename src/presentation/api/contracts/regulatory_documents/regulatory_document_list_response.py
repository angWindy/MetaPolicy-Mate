from pydantic import BaseModel

from src.presentation.api.contracts.regulatory_documents.regulatory_document_response import (
    RegulatoryDocumentResponse,
)


class RegulatoryDocumentListResponse(
    BaseModel
):
    items: list[
        RegulatoryDocumentResponse
    ]

    total: int
    page: int
    page_size: int