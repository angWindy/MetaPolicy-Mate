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
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.static_thresholds.create.create_static_threshold_command import (
    CreateStaticThresholdCommand,
)
from src.application.features.static_thresholds.static_threshold_dto import (
    StaticThresholdDto,
)
from src.domain.entities.static_threshold import (
    StaticThreshold,
)
from src.domain.enums.static_threshold_status import (
    StaticThresholdStatus,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.domain.repositories.document_section_repository import (
    DocumentSectionRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)


ALLOWED_OPERATORS = {
    "<",
    "<=",
    "=",
    ">=",
    ">",
}


class CreateStaticThresholdHandler(
    RequestHandler[
        CreateStaticThresholdCommand,
        StaticThresholdDto,
    ]
):
    def __init__(
        self,
        section_repository: (
            DocumentSectionRepository
        ),
        section_version_repository: (
            DocumentSectionVersionRepository
        ),
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
        threshold_repository: (
            StaticThresholdRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._section_repository = (
            section_repository
        )

        self._section_version_repository = (
            section_version_repository
        )

        self._section_metadata_repository = (
            section_metadata_repository
        )

        self._threshold_repository = (
            threshold_repository
        )

        self._unit_of_work = unit_of_work

    async def handle(
        self,
        request: (
            CreateStaticThresholdCommand
        ),
    ) -> StaticThresholdDto:
        threshold_key = (
            request.threshold_key
            .strip()
            .upper()
        )

        scope_key = (
            request.scope_key
            .strip()
            .upper()
        )

        name = request.name.strip()

        operator = (
            request.operator.strip()
        )

        unit = (
            request.unit.strip()
            if request.unit
            and request.unit.strip()
            else None
        )

        condition_text = (
            request.condition_text.strip()
        )

        if not threshold_key:
            raise ConflictException(
                "Threshold key is required."
            )

        if not scope_key:
            raise ConflictException(
                "Threshold scope key "
                "is required."
            )

        if not name:
            raise ConflictException(
                "Threshold name is required."
            )

        if operator not in ALLOWED_OPERATORS:
            raise ConflictException(
                "Invalid threshold operator."
            )

        if not condition_text:
            raise ConflictException(
                "Threshold application "
                "condition is required."
            )

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

        section_version = await (
            self._section_version_repository
            .get_by_id(
                request.section_version_id
            )
        )

        if section_version is None:
            raise NotFoundException(
                "Document section version "
                "not found."
            )

        if (
            section_version.section_id
            != section.id
        ):
            raise ConflictException(
                "Section version does not "
                "belong to this section."
            )

        if not section_version.is_current:
            raise ConflictException(
                "Threshold must reference "
                "the current section version."
            )

        metadata_approved = await (
            self._section_metadata_repository
            .is_section_fully_approved(
                section.id
            )
        )

        if not metadata_approved:
            raise ConflictException(
                "Section metadata must be "
                "fully approved before "
                "creating a static threshold."
            )

        next_version_number = await (
            self._threshold_repository
            .get_next_version_number(
                threshold_key,
                scope_key,
            )
        )

        threshold = StaticThreshold(
            id=uuid4(),
            threshold_key=threshold_key,
            scope_key=scope_key,
            version_number=(
                next_version_number
            ),
            name=name,
            operator=operator,
            value=request.value,
            unit=unit,
            condition_text=condition_text,
            section_id=section.id,
            section_version_id=(
                section_version.id
            ),
            status=(
                StaticThresholdStatus.DRAFT
            ),
            is_current=False,
            verified_at=None,
            created_at=datetime.now(
                timezone.utc
            ),
            updated_at=None,
        )

        await (
            self._threshold_repository
            .add(threshold)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            StaticThresholdDto
            .from_entity(threshold)
        )