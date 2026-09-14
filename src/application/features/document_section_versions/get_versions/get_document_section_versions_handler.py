from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_section_versions.document_section_version_dto import (
    DocumentSectionVersionDto,
)
from src.application.features.document_section_versions.get_versions.get_document_section_versions_query import (
    GetDocumentSectionVersionsQuery,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)


class GetDocumentSectionVersionsHandler(
    RequestHandler[
        GetDocumentSectionVersionsQuery,
        list[DocumentSectionVersionDto],
    ]
):
    def __init__(
        self,
        document_section_repository: (
            DocumentSectionRepository
        ),
        document_section_version_repository: (
            DocumentSectionVersionRepository
        ),
    ) -> None:
        self._section_repository = (
            document_section_repository
        )

        self._version_repository = (
            document_section_version_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentSectionVersionsQuery
        ),
    ) -> list[
        DocumentSectionVersionDto
    ]:
        section = await (
            self._section_repository
            .get_by_id(
                request.section_id
            )
        )

        if section is None:
            raise NotFoundException(
                "Document section not found."
            )

        versions = await (
            self._version_repository
            .get_by_section_id(
                section.id
            )
        )

        return [
            DocumentSectionVersionDto(
                id=item.id,
                section_id=(
                    item.section_id
                ),
                version_number=(
                    item.version_number
                ),
                content=item.content,
                effective_from=(
                    item.effective_from
                ),
                effective_to=(
                    item.effective_to
                ),
                is_current=(
                    item.is_current
                ),
                created_at=(
                    item.created_at
                ),
                updated_at=(
                    item.updated_at
                ),
            )
            for item in versions
        ]