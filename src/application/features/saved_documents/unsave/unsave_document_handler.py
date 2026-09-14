from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.saved_documents.unsave.unsave_document_command import (
    UnsaveDocumentCommand,
)
from src.domain.repositories.saved_document_repository import (
    SavedDocumentRepository,
)


class UnsaveDocumentHandler(
    RequestHandler[
        UnsaveDocumentCommand,
        None,
    ]
):
    def __init__(
        self,
        saved_repository: SavedDocumentRepository,
    ) -> None:
        self._saved_repository = saved_repository

    async def handle(
        self,
        request: UnsaveDocumentCommand,
    ) -> None:
        deleted = await self._saved_repository.delete(
            user_id=request.user_id,
            document_id=request.document_id,
        )
        if not deleted:
            raise NotFoundException(
                "Saved document not found."
            )
