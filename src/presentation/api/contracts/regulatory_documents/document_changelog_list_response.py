from pydantic import BaseModel

from src.presentation.api.contracts.regulatory_documents.document_changelog_response import (
    DocumentChangelogResponse,
)


class DocumentChangelogListResponse(
    BaseModel
):
    items: list[
        DocumentChangelogResponse
    ]

    total: int
    page: int
    page_size: int