from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)
from src.application.features.regulatory_documents.get_detail.get_regulatory_document_query import (
    GetRegulatoryDocumentQuery,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetRegulatoryDocumentHandler(
    RequestHandler[
        GetRegulatoryDocumentQuery,
        RegulatoryDocumentItem,
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
    ) -> None:
        self._document_repository = (
            document_repository
        )

    async def handle(
        self,
        request: GetRegulatoryDocumentQuery,
    ) -> RegulatoryDocumentItem:
        document = (
            await self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document not found."
            )

        return (
            RegulatoryDocumentItem
            .from_document(
                document
            )
        )