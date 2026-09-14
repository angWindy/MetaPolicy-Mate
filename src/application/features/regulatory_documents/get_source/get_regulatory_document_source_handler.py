from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.file_storage import (
    FileStorage,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.get_source.get_regulatory_document_source_query import (
    GetRegulatoryDocumentSourceQuery,
    GetRegulatoryDocumentSourceResult,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class GetRegulatoryDocumentSourceHandler(
    RequestHandler[
        GetRegulatoryDocumentSourceQuery,
        GetRegulatoryDocumentSourceResult,
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        document_version_repository: (
            DocumentVersionRepository
        ),
        file_storage: FileStorage,
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._document_version_repository = (
            document_version_repository
        )

        self._file_storage = (
            file_storage
        )

    async def handle(
        self,
        request: (
            GetRegulatoryDocumentSourceQuery
        ),
    ) -> GetRegulatoryDocumentSourceResult:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document not found."
            )

        version = await (
            self
            ._document_version_repository
            .get_latest_by_document_id(
                document.id
            )
        )

        if version is None:
            raise NotFoundException(
                "Document source was not found."
            )

        content = await (
            self._file_storage.download(
                version.object_key
            )
        )

        return (
            GetRegulatoryDocumentSourceResult(
                content=content,
                source_filename=(
                    version.source_filename
                ),
                content_type=(
                    version.content_type
                    or "application/pdf"
                ),
            )
        )