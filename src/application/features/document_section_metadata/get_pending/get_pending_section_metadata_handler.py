from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_section_metadata.common.section_metadata_draft_item import (
    SectionMetadataDraftItem,
)
from src.application.features.document_section_metadata.get_pending.get_pending_section_metadata_query import (
    GetPendingSectionMetadataQuery,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.domain.repositories.document_version_repository import (
    DocumentVersionRepository,
)


class GetPendingSectionMetadataHandler(
    RequestHandler[
        GetPendingSectionMetadataQuery,
        list[SectionMetadataDraftItem],
    ]
):
    def __init__(
        self,
        document_repository: (
            DocumentRepository
        ),
        document_version_repository: (
            DocumentVersionRepository
        ),
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
    ) -> None:
        self._document_repository = (
            document_repository
        )

        self._version_repository = (
            document_version_repository
        )

        self._section_metadata_repository = (
            section_metadata_repository
        )

    async def handle(
        self,
        request: (
            GetPendingSectionMetadataQuery
        ),
    ) -> list[
        SectionMetadataDraftItem
    ]:
        document = await (
            self._document_repository
            .get_by_id(
                request.document_id
            )
        )

        if document is None:
            raise NotFoundException(
                "Regulatory document not found."
            )

        version = await (
            self._version_repository
            .get_by_id(
                request.version_id
            )
        )

        if version is None:
            raise NotFoundException(
                "Document version not found."
            )

        if (
            version.document_id
            != document.id
        ):
            raise ConflictException(
                "Document version does not "
                "belong to this document."
            )

        drafts = await (
            self._section_metadata_repository
            .get_pending_by_version(
                version.id
            )
        )

        return [
            SectionMetadataDraftItem
            .from_entity(item)
            for item in drafts
        ]