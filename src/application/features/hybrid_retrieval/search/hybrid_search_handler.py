from uuid import UUID

from src.application.common.exceptions.request_validation_exception import (
    RequestValidationException,
)
from src.application.common.interfaces.hybrid_retrieval_service import (
    HybridRetrievalActor,
    HybridRetrievalService,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.hybrid_retrieval.search.hybrid_search_query import (
    HybridSearchQuery,
)
from src.application.features.hybrid_retrieval.search.hybrid_search_result import (
    HybridSearchItemDto,
    HybridSearchResult,
)
from src.domain.enums.document_access_scope import (
    DocumentAccessScope,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.shared.validation_error import (
    ValidationError,
)


class HybridSearchHandler(
    RequestHandler[
        HybridSearchQuery,
        HybridSearchResult,
    ]
):
    def __init__(
        self,
        hybrid_retrieval_service: (
            HybridRetrievalService
        ),
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
    ) -> None:
        self._hybrid_retrieval_service = (
            hybrid_retrieval_service
        )

        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

    async def handle(
        self,
        request: HybridSearchQuery,
    ) -> HybridSearchResult:
        query = request.query.strip()

        if not query:
            raise RequestValidationException(
                [
                    ValidationError(
                        property_name="query",
                        error_message=(
                            "Search query "
                            "is required."
                        ),
                    )
                ]
            )

        department = (
            request.department.strip()
        )

        items = await (
            self._hybrid_retrieval_service
            .search(
                query=query,
                actor=(
                    HybridRetrievalActor(
                        user_id=(
                            request.user_id
                        ),
                        department=(
                            department
                        ),
                        roles=(
                            request.roles
                        ),
                    )
                ),
                as_of_date=(
                    request.as_of_date
                ),
            )
        )

        accessible_items: list = []

        access_cache: dict[
            UUID,
            bool,
        ] = {}

        for item in items:
            document_id_value = (
                item.metadata.get(
                    "document_id"
                )
            )

            if (
                document_id_value
                is None
            ):
                # Fail closed.
                continue

            try:
                document_id = UUID(
                    str(
                        document_id_value
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            if (
                document_id
                in access_cache
            ):
                if (
                    access_cache[
                        document_id
                    ]
                ):
                    accessible_items.append(
                        item
                    )

                continue

            document = await (
                self._document_repository
                .get_by_id(
                    document_id
                )
            )

            if document is None:
                access_cache[
                    document_id
                ] = False

                continue

            if (
                document.access_scope
                == (
                    DocumentAccessScope
                    .PUBLIC
                )
            ):
                allowed = True

            elif (
                request.department_id
                is None
            ):
                allowed = False

            else:
                allowed = await (
                    self
                    ._document_department_repository
                    .can_access(
                        document_id=(
                            document.id
                        ),
                        department_id=(
                            request
                            .department_id
                        ),
                    )
                )

            access_cache[
                document_id
            ] = allowed

            if allowed:
                accessible_items.append(
                    item
                )

        return HybridSearchResult(
            query=query,
            has_evidence=bool(
                accessible_items
            ),
            items=[
                HybridSearchItemDto(
                    chunk_id=(
                        item.chunk_id
                    ),
                    text=item.text,
                    score=item.score,
                    source=item.source,
                    metadata=item.metadata,
                )
                for item
                in accessible_items
            ],
        )