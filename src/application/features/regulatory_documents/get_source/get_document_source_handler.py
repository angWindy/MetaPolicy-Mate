from __future__ import annotations

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.get_source.get_document_source_query import (
    GetDocumentSourceQuery,
)
from src.application.features.regulatory_documents.get_source.get_document_source_result import (
    GetDocumentSourceResult,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class GetDocumentSourceHandler(
    RequestHandler[
        GetDocumentSourceQuery,
        GetDocumentSourceResult,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_version_repository: (
            DocumentVersionRepository
        ),
        file_storage: FileStorage,
        request_context: RequestContext,
    ) -> None:
        self._document_repository = (
            document_repository
        )
        self._document_version_repository = (
            document_version_repository
        )
        self._file_storage = file_storage
        self._request_context = (
            request_context
        )

    async def handle(
        self,
        request: GetDocumentSourceQuery,
    ) -> GetDocumentSourceResult:
        school_id = (
            self._request_context.school_id
        )

        document = (
            await self._document_repository
            .get_by_id(
                request.document_id,
                school_id=school_id,
            )
        )
        if document is None:
            raise NotFoundException(
                f"Document {request.document_id} not found."
            )

        version = (
            await self
            ._document_version_repository
            .get_latest_by_document_id(
                request.document_id
            )
        )
        if version is None:
            raise NotFoundException(
                "No version found for "
                f"document {request.document_id}."
            )

        content = (
            await self._file_storage.download(
                version.object_key
            )
        )

        return GetDocumentSourceResult(
            content=content,
            content_type=version.content_type,
            filename=version.source_filename,
        )
