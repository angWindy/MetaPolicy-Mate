from src.application.common.document_access_policy import (
    can_access_document,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_effectiveness_alerts.due_documents.get_documents_due_for_effectiveness_query import (
    GetDocumentsDueForEffectivenessQuery,
)
from src.application.features.regulatory_documents.common.regulatory_document_item import (
    RegulatoryDocumentItem,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetDocumentsDueForEffectivenessHandler(
    RequestHandler[
        GetDocumentsDueForEffectivenessQuery,
        list[
            RegulatoryDocumentItem
        ],
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentsDueForEffectivenessQuery
        ),
    ) -> list[
        RegulatoryDocumentItem
    ]:
        documents = await (
            self._document_repository
            .get_documents_due_for_effectiveness(
                request.as_of
            )
        )

        result: list[
            RegulatoryDocumentItem
        ] = []

        for document in documents:
            allowed = await (
                can_access_document(
                    document_id=(
                        document.id
                    ),
                    department_id=(
                        request.department_id
                    ),
                    document_repository=(
                        self
                        ._document_repository
                    ),
                    document_department_repository=(
                        self
                        ._document_department_repository
                    ),
                )
            )

            if not allowed:
                continue

            result.append(
                RegulatoryDocumentItem
                .from_document(
                    document
                )
            )

        return result