from datetime import datetime, timezone
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.saved_documents.save.save_document_command import (
    SaveDocumentCommand,
)
from src.application.features.saved_documents.save.save_document_result import (
    SaveDocumentResult,
)
from src.domain.entities.saved_document import (
    SavedDocument,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.saved_document_repository import (
    SavedDocumentRepository,
)


class SaveDocumentHandler(
    RequestHandler[
        SaveDocumentCommand,
        SaveDocumentResult,
    ]
):
    def __init__(
        self,
        saved_repository: SavedDocumentRepository,
        document_repository: DocumentRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._saved_repository = saved_repository
        self._document_repository = document_repository
        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: SaveDocumentCommand,
    ) -> SaveDocumentResult:
        # Verify document exists
        document = await self._document_repository.get_by_id(
            request.document_id
        )
        if document is None:
            raise NotFoundException(
                "Document not found."
            )

        # Check duplicate
        already_exists = (
            await self._saved_repository.check_exists(
                user_id=request.user_id,
                document_id=request.document_id,
            )
        )
        if already_exists:
            raise ConflictException(
                "Document already saved."
            )

        now = datetime.now(timezone.utc)
        saved = SavedDocument(
            id=uuid4(),
            user_id=request.user_id,
            document_id=request.document_id,
            created_at=now,
        )

        await self._saved_repository.add(saved)
        await self._unit_of_work.save_changes()

        return SaveDocumentResult(
            id=saved.id,
            user_id=saved.user_id,
            document_id=saved.document_id,
            created_at=saved.created_at,
        )
