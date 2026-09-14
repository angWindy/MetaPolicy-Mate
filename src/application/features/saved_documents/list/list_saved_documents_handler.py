from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.saved_documents.list.list_saved_documents_query import (
    ListSavedDocumentsQuery,
)
from src.application.features.saved_documents.list.list_saved_documents_result import (
    ListSavedDocumentsResult,
    SavedDocumentItem,
)
from src.domain.repositories.saved_document_repository import (
    SavedDocumentRepository,
)


class ListSavedDocumentsHandler(
    RequestHandler[
        ListSavedDocumentsQuery,
        ListSavedDocumentsResult,
    ]
):
    def __init__(
        self,
        saved_repository: SavedDocumentRepository,
    ) -> None:
        self._saved_repository = saved_repository

    async def handle(
        self,
        request: ListSavedDocumentsQuery,
    ) -> ListSavedDocumentsResult:
        items, total = await (
            self._saved_repository.list_by_user(
                user_id=request.user_id,
                page=request.page,
                page_size=request.page_size,
            )
        )

        return ListSavedDocumentsResult(
            items=[
                SavedDocumentItem(
                    id=item.id,
                    document_id=item.document_id,
                    created_at=item.created_at,
                )
                for item in items
            ],
            total=total,
            page=request.page,
            page_size=request.page_size,
        )
