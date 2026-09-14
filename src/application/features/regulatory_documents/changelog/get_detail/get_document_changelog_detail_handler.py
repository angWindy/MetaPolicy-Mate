from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.changelog.common.document_changelog_item import (
    DocumentChangelogItem,
)
from src.application.features.regulatory_documents.changelog.get_detail.get_document_changelog_detail_query import (
    GetDocumentChangelogDetailQuery,
)
from src.domain.repositories.document_changelog_repository import (
    DocumentChangelogRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class GetDocumentChangelogDetailHandler(
    RequestHandler[
        GetDocumentChangelogDetailQuery,
        DocumentChangelogItem,
    ]
):
    def __init__(
        self,
        changelog_repository: (
            DocumentChangelogRepository
        ),
        document_repository: (
            DocumentRepository
        ),
    ) -> None:
        self._changelog_repository = (
            changelog_repository
        )

        self._document_repository = (
            document_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentChangelogDetailQuery
        ),
    ) -> DocumentChangelogItem:
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

        changelog = (
            await self
            ._changelog_repository
            .get_by_id(
                document_id=(
                    request.document_id
                ),
                changelog_id=(
                    request.changelog_id
                ),
            )
        )

        if changelog is None:
            raise NotFoundException(
                "Document changelog "
                "entry not found."
            )

        return (
            DocumentChangelogItem
            .from_entity(changelog)
        )