from datetime import (
    datetime,
    timezone,
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
from src.application.features.document_effectiveness_alerts.common.document_effectiveness_alert_item import (
    DocumentEffectivenessAlertItem,
)
from src.application.features.document_effectiveness_alerts.update_status.update_document_effectiveness_alert_status_command import (
    UpdateDocumentEffectivenessAlertStatusCommand,
)
from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)


class UpdateDocumentEffectivenessAlertStatusHandler(
    RequestHandler[
        UpdateDocumentEffectivenessAlertStatusCommand,
        DocumentEffectivenessAlertItem,
    ]
):
    def __init__(
        self,
        alert_repository: (
            DocumentEffectivenessAlertRepository
        ),
        unit_of_work: UnitOfWork,
    ) -> None:
        self._alert_repository = (
            alert_repository
        )
        self._unit_of_work = (
            unit_of_work
        )

    async def handle(
        self,
        request: (
            UpdateDocumentEffectivenessAlertStatusCommand
        ),
    ) -> DocumentEffectivenessAlertItem:
        alert = (
            await self._alert_repository
            .get_by_id(
                request.alert_id
            )
        )

        if alert is None:
            raise NotFoundException(
                "Effectiveness alert not found."
            )

        # Snapshot trước khi thay đổi.
        request.set_audit_before(
            {
                "alert_id":
                    alert.id,
                "affected_document_id":
                    alert.affected_document_id,
                "status":
                    alert.status.value,
                "operation":
                    "effectiveness_alert_status_updated",
            }
        )

        alert.status = request.status

        alert.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await (
            self._alert_repository
            .update(alert)
        )

        await (
            self._unit_of_work
            .save_changes()
        )

        return (
            DocumentEffectivenessAlertItem
            .from_entity(alert)
        )