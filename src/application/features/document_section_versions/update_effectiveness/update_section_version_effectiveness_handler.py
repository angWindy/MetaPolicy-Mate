from datetime import (
    datetime,
    timezone,
)

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
from src.application.features.document_section_versions.document_section_version_dto import (
    DocumentSectionVersionDto,
)
from src.application.features.document_section_versions.update_effectiveness.update_section_version_effectiveness_command import (
    UpdateSectionVersionEffectivenessCommand,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)


class UpdateSectionVersionEffectivenessHandler(
    RequestHandler[
        UpdateSectionVersionEffectivenessCommand,
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
        self._section_repository = (
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
            UpdateSectionVersionEffectivenessCommand
        ),
    ) -> DocumentSectionVersionDto:
        section = await (
            self._section_repository
            .get_by_id_for_update(
                request.section_id
            )
        )

        if section is None:
            raise NotFoundException(
                "Document section not found."
            )

        version = await (
            self._version_repository
            .get_by_id(
                request.version_id
            )
        )

        if version is None:
            raise NotFoundException(
                "Document section version "
                "not found."
            )

        if (
            version.section_id
            != section.id
        ):
            raise ConflictException(
                "Section version does not "
                "belong to this section."
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
                exclude_version_id=(
                    version.id
                ),
            )
        )

        if has_overlap:
            raise ConflictException(
                "Effective period overlaps "
                "an existing section version."
            )

        if request.is_current:
            current = await (
                self._version_repository
                .get_current(
                    section.id
                )
            )

            if (
                current is not None
                and current.id
                != version.id
            ):
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

                await (
                    self._unit_of_work
                    .flush()
                )

        version.effective_from = (
            request.effective_from
        )

        version.effective_to = (
            request.effective_to
        )

        version.is_current = (
            request.is_current
        )

        version.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await (
            self._version_repository
            .update(
                version
            )
        )

        # reindex_section() query DB bằng
        # cùng AsyncSession, nên flush trước.
        await (
            self._unit_of_work
            .flush()
        )

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