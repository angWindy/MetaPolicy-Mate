from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)
from src.application.features.regulatory_documents.get_list.get_regulatory_documents_query import (
    GetRegulatoryDocumentsQuery,
)
from src.application.features.regulatory_documents.get_list.get_regulatory_documents_result import (
    GetRegulatoryDocumentsResult,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetRegulatoryDocumentsHandler(
    RequestHandler[
        GetRegulatoryDocumentsQuery,
        GetRegulatoryDocumentsResult,
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
        request: GetRegulatoryDocumentsQuery,
    ) -> GetRegulatoryDocumentsResult:
        page = max(
            request.page,
            1,
        )

        page_size = min(
            max(
                request.page_size,
                1,
            ),
            100,
        )

        skip = (
            page - 1
        ) * page_size

        documents = await (
            self._document_repository
            .search(
                document_number=(
                    request.document_number
                ),
                legal_status=(
                    request.legal_status
                ),
                issued_from=(
                    request.issued_from
                ),
                issued_to=(
                    request.issued_to
                ),
                department_id=(
                    request.department_id
                ),
                skip=skip,
                limit=page_size,
                is_admin=request.is_admin,
            )
        )

        total = await (
            self._document_repository
            .count(
                document_number=(
                    request.document_number
                ),
                legal_status=(
                    request.legal_status
                ),
                issued_from=(
                    request.issued_from
                ),
                issued_to=(
                    request.issued_to
                ),
                department_id=(
                    request.department_id
                ),
                is_admin=request.is_admin,
            )
        )

        return GetRegulatoryDocumentsResult(
            items=[
                RegulatoryDocumentItem
                .from_document(document)
                for document in documents
            ],
            total=total,
            page=page,
            page_size=page_size,
        )