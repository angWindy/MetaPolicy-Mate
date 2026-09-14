from pydantic import BaseModel

from src.presentation.api.contracts.document_effectiveness_alerts.document_effectiveness_alert_response import (
    DocumentEffectivenessAlertResponse,
)


class DocumentEffectivenessAlertListResponse(
    BaseModel
):
    items: list[
        DocumentEffectivenessAlertResponse
    ]

    total: int
    page: int
    page_size: int