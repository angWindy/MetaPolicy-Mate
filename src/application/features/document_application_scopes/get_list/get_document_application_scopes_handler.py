from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_application_scopes.common.document_application_scope_item import (
    DocumentApplicationScopeItem,
)
from src.application.features.document_application_scopes.get_list.get_document_application_scopes_query import (
    GetDocumentApplicationScopesQuery,
)
from src.domain.repositories.document_application_scope_repository import (
    DocumentApplicationScopeRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetDocumentApplicationScopesHandler(
    RequestHandler[
        GetDocumentApplicationScopesQuery,
        list[
            DocumentApplicationScopeItem
        ],
    ]
):
    def __init__(
        self,
        application_scope_repository: (
            DocumentApplicationScopeRepository
        ),
        document_repository: (
            DocumentRepository
        ),
    ) -> None:
        self._application_scope_repository = (
            application_scope_repository
        )

        self._document_repository = (
            document_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentApplicationScopesQuery
        ),
    ) -> list[
        DocumentApplicationScopeItem
    ]:
        document = (
            await self
            ._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document "
                "not found."
            )

        scopes = (
            await self
            ._application_scope_repository
            .get_by_document_id(
                request.document_id
            )
        )

        return [
            DocumentApplicationScopeItem
            .from_entity(scope)
            for scope in scopes
        ]