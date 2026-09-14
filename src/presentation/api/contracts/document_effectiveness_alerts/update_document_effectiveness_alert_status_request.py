from pydantic import BaseModel

from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


class UpdateDocumentEffectivenessAlertStatusRequest(
    BaseModel
):
    status: (
        DocumentEffectivenessAlertStatus
    )