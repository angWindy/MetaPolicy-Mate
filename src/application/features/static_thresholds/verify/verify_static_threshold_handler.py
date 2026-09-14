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
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.static_thresholds.static_threshold_dto import (
    StaticThresholdDto,
)
from src.application.features.static_thresholds.verify.verify_static_threshold_command import (
    VerifyStaticThresholdCommand,
)
from src.domain.enums.static_threshold_status import (
    StaticThresholdStatus,
)
from src.domain.repositories.document_section_metadata_draft_repository import (
    DocumentSectionMetadataDraftRepository,
)
from src.domain.repositories.document_section_version_repository import (
    DocumentSectionVersionRepository,
)
from src.domain.repositories.static_threshold_repository import (
    StaticThresholdRepository,
)


class VerifyStaticThresholdHandler(
    RequestHandler[
        VerifyStaticThresholdCommand,
        StaticThresholdDto,
    ]
):
    def __init__(
        self,
        threshold_repository: (
            StaticThresholdRepository
        ),
        section_version_repository: (
            DocumentSectionVersionRepository
        ),
        section_metadata_repository: (
            DocumentSectionMetadataDraftRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._threshold_repository = (
            threshold_repository
        )

        self._section_version_repository = (
            section_version_repository
        )

        self._section_metadata_repository = (
            section_metadata_repository
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            VerifyStaticThresholdCommand
        ),
    ) -> StaticThresholdDto:
        threshold = await (
            self._threshold_repository
            .get_by_id(
                request.threshold_id
            )
        )

        if threshold is None:
            raise NotFoundException(
                "Static threshold not found."
            )

        if (
            threshold.status
            == (
                StaticThresholdStatus
                .VERIFIED
            )
        ):
            raise ConflictException(
                "Static threshold has "
                "already been verified."
            )

        section_version = await (
            self._section_version_repository
            .get_by_id(
                threshold.section_version_id
            )
        )

        if section_version is None:
            raise NotFoundException(
                "Source section version "
                "not found."
            )

        if (
            section_version.section_id
            != threshold.section_id
        ):
            raise ConflictException(
                "Threshold source "
                "reference is invalid."
            )

        if not section_version.is_current:
            raise ConflictException(
                "Threshold source section "
                "version is no longer current."
            )

        metadata_approved = await (
            self._section_metadata_repository
            .is_section_fully_approved(
                threshold.section_id
            )
        )

        if not metadata_approved:
            raise ConflictException(
                "Section metadata must be "
                "fully approved before "
                "verifying this threshold."
            )

        old_current = await (
            self._threshold_repository
            .get_current(
                threshold.threshold_key,
                threshold.scope_key,
            )
        )

        if (
            old_current is not None
            and old_current.id
            != threshold.id
        ):
            if not request.confirm_replacement:
                raise ConflictException(
                    "A verified threshold already "
                    "exists for this threshold key "
                    "and scope. Explicit "
                    "confirmation is required "
                    "to replace it."
                )

            old_current.is_current = False

            old_current.updated_at = (
                datetime.now(
                    timezone.utc
                )
            )

            await (
                self._threshold_repository
                .update(old_current)
            )

            await (
                self._unit_of_work
                .flush()
            )


        now = datetime.now(
            timezone.utc
        )

        threshold.status = (
            StaticThresholdStatus
            .VERIFIED
        )

        threshold.is_current = True

        threshold.verified_at = now
        threshold.updated_at = now

        await (
            self._threshold_repository
            .update(threshold)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            StaticThresholdDto
            .from_entity(threshold)
        )