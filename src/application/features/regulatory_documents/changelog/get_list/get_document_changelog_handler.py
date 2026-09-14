from dataclasses import dataclass

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.regulatory_documents.changelog.common.document_changelog_item import (
    DocumentChangelogItem,
)
from src.application.features.regulatory_documents.changelog.get_list.get_document_changelog_query import (
    GetDocumentChangelogQuery,
)
from src.domain.repositories.document_changelog_repository import (
    DocumentChangelogRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


@dataclass(frozen=True)
class DocumentChangelogListResult:
    items: list[
        DocumentChangelogItem
    ]

    total: int
    page: int
    page_size: int


class GetDocumentChangelogHandler(
    RequestHandler[
        GetDocumentChangelogQuery,
        DocumentChangelogListResult,
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
        request: GetDocumentChangelogQuery,
    ) -> DocumentChangelogListResult:
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

        skip = (
            request.page - 1
        ) * request.page_size

        items = (
            await self
            ._changelog_repository
            .get_by_document_id(
                document_id=(
                    request.document_id
                ),
                action=request.action,
                from_at=request.from_at,
                to_at=request.to_at,
                skip=skip,
                limit=request.page_size,
            )
        )

        total = (
            await self
            ._changelog_repository
            .count_by_document_id(
                document_id=(
                    request.document_id
                ),
                action=request.action,
                from_at=request.from_at,
                to_at=request.to_at,
            )
        )

        return (
            DocumentChangelogListResult(
                items=[
                    DocumentChangelogItem
                    .from_entity(item)
                    for item in items
                ],

                total=total,

                page=request.page,

                page_size=(
                    request.page_size
                ),
            )
        )