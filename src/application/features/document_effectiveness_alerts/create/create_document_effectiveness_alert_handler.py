from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.common.interfaces.request_context import (
    RequestContext,
)
from src.application.common.interfaces.unit_of_work import (
    UnitOfWork,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_effectiveness_alerts.common.document_effectiveness_alert_item import (
    DocumentEffectivenessAlertItem,
)
from src.application.features.document_effectiveness_alerts.create.create_document_effectiveness_alert_command import (
    CreateDocumentEffectivenessAlertCommand,
)
from src.domain.entities.document_effectiveness_alert import (
    DocumentEffectivenessAlert,
)
from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)
from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


class CreateDocumentEffectivenessAlertHandler(
    RequestHandler[
        CreateDocumentEffectivenessAlertCommand,
        DocumentEffectivenessAlertItem,
    ]
):
    def __init__(
        self,
        alert_repository: (
            DocumentEffectivenessAlertRepository
        ),
        document_repository: (
            DocumentRepository
        ),
        request_context: RequestContext,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._alert_repository = (
            alert_repository
        )

        self._document_repository = (
            document_repository
        )

        self._request_context = (
            request_context
        )

        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            CreateDocumentEffectivenessAlertCommand
        ),
    ) -> DocumentEffectivenessAlertItem:
        affected_document = (
            await self._document_repository
            .get_by_id(
                request.affected_document_id
            )
        )

        if affected_document is None:
            raise NotFoundException(
                "Affected regulatory "
                "document not found."
            )

        now = datetime.now(
            timezone.utc
        )

        alert = (
            DocumentEffectivenessAlert(
                id=uuid4(),

                new_document_number=(
                    request
                    .new_document_number
                    .strip()
                ),

                new_document_title=(
                    request
                    .new_document_title
                    .strip()
                ),

                announced_date=(
                    request.announced_date
                ),

                effective_date=(
                    request.effective_date
                ),

                affected_document_id=(
                    request
                    .affected_document_id
                ),

                status=(
                    DocumentEffectivenessAlertStatus
                    .CHO_XU_LY
                ),

                note=(
                    request.note.strip()
                    if request.note
                    else None
                ),

                created_by=(
                    self._request_context
                    .user_id
                ),

                created_at=now,

                updated_at=None,
            )
        )

        await self._alert_repository.add(
            alert
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DocumentEffectivenessAlertItem
            .from_entity(alert)
        )