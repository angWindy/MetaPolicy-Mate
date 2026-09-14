from pydantic import BaseModel

from src.presentation.api.contracts.saved_documents.saved_document_response import (
    SavedDocumentResponse,
)


class SavedDocumentListResponse(BaseModel):
    items: list[SavedDocumentResponse]
    total: int
    page: int
    page_size: int
