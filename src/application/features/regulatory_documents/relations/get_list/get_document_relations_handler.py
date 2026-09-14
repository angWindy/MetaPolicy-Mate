from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.relations.get_list.get_document_relations_query import (
    GetDocumentRelationsQuery,
)
from src.domain.entities.document_relation import (
    DocumentRelation,
)
from src.domain.repositories.document_relation_repository import (
    DocumentRelationRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetDocumentRelationsHandler(
    RequestHandler[
        GetDocumentRelationsQuery,
        list[DocumentRelation],
    ]
):
    def __init__(
        self,
        document_repository: DocumentRepository,
        document_relation_repository: (
            DocumentRelationRepository
        ),
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._document_relation_repository = (
            document_relation_repository
        )

    async def handle(
        self,
        request: GetDocumentRelationsQuery,
    ) -> list[DocumentRelation]:
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
            await self
            ._document_relation_repository
            .get_by_document_id(
                request.document_id
            )
        )