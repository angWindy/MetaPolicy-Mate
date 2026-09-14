from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.rag_index_service import (
    RagIndexService,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_section_versions.create.create_document_section_version_command import (
    CreateDocumentSectionVersionCommand,
)
from src.application.features.document_section_versions.document_section_version_dto import (
    DocumentSectionVersionDto,
)
from src.domain.entities.document_section_version import (
    DocumentSectionVersion,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)


class CreateDocumentSectionVersionHandler(
    RequestHandler[
        CreateDocumentSectionVersionCommand,
        DocumentSectionVersionDto,
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
        rag_index_service: (
            RagIndexService
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._document_section_repository = (
            document_section_repository
        )

        self._version_repository = (
            document_section_version_repository
        )

        self._rag_index_service = (
            rag_index_service
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            CreateDocumentSectionVersionCommand
        ),
    ) -> DocumentSectionVersionDto:
        # Lock section trong cùng transaction.
        # Hai request tạo version cho cùng
        # section không thể cùng chạy
        # overlap-check/version-number.
        section = await (
            self._document_section_repository
            .get_by_id_for_update(
                request.section_id
            )
        )

        if section is None:
            raise NotFoundException(
                "Document section not found."
            )

        content = (
            request.content.strip()
        )

        if not content:
            raise ConflictException(
                "Section content is required."
            )

        if (
            request.effective_to
            is not None
            and request.effective_from
            > request.effective_to
        ):
            raise ConflictException(
                "Effective from must be "
                "less than or equal to "
                "effective to."
            )

        has_overlap = await (
            self._version_repository
            .has_overlapping_effective_period(
                section_id=section.id,
                effective_from=(
                    request.effective_from
                ),
                effective_to=(
                    request.effective_to
                ),
            )
        )

        if has_overlap:
            raise ConflictException(
                "Effective period overlaps "
                "an existing section version."
            )

        next_version_number = await (
            self._version_repository
            .get_next_version_number(
                section.id
            )
        )

        if request.is_current:
            current = await (
                self._version_repository
                .get_current(
                    section.id
                )
            )

            if current is not None:
                current.is_current = False

                current.updated_at = (
                    datetime.now(
                        timezone.utc
                    )
                )

                await (
                    self._version_repository
                    .update(
                        current
                    )
                )

                # Tránh partial unique index
                # thấy hai current=true.
                await (
                    self._unit_of_work
                    .flush()
                )

        now = datetime.now(
            timezone.utc
        )

        version = (
            DocumentSectionVersion(
                id=uuid4(),
                section_id=(
                    section.id
                ),
                version_number=(
                    next_version_number
                ),
                content=content,
                effective_from=(
                    request.effective_from
                ),
                effective_to=(
                    request.effective_to
                ),
                is_current=(
                    request.is_current
                ),
                created_at=now,
                updated_at=None,
            )
        )

        await (
            self._version_repository
            .add(
                version
            )
        )

        # Cho cùng AsyncSession nhìn thấy
        # version mới nhưng chưa commit.
        await (
            self._unit_of_work
            .flush()
        )

        # PostgreSQL vẫn là
        # source-of-truth.
        # Qdrant/memory chỉ là index.
        await (
            self._rag_index_service
            .reindex_section(
                section_id=(
                    section.id
                )
            )
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DocumentSectionVersionDto(
                id=version.id,
                section_id=(
                    version.section_id
                ),
                version_number=(
                    version.version_number
                ),
                content=(
                    version.content
                ),
                effective_from=(
                    version.effective_from
                ),
                effective_to=(
                    version.effective_to
                ),
                is_current=(
                    version.is_current
                ),
                created_at=(
                    version.created_at
                ),
                updated_at=(
                    version.updated_at
                ),
            )
        )