from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.get_sections.document_section_item import (
    DocumentSectionItem,
)
from src.application.features.regulatory_documents.get_sections.get_document_sections_query import (
    GetDocumentSectionsQuery,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)


class GetDocumentSectionsHandler(
    RequestHandler[
        GetDocumentSectionsQuery,
        list[DocumentSectionItem],
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_section_repository: (
            DocumentSectionRepository
        ),
    ) -> None:
        self._document_repository = (
            document_repository
        )
        self._document_section_repository = (
            document_section_repository
        )

    async def handle(
        self,
        request: GetDocumentSectionsQuery,
    ) -> list[DocumentSectionItem]:
        document = await (
            self._document_repository.get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Document not found."
            )

        sections = await (
            self
            ._document_section_repository
            .list_by_document(document.id)
        )

        return [
            DocumentSectionItem.from_domain(s)
            for s in sections
        ]
