from typing import Protocol
from uuid import UUID

from src.domain.entities.document_effectiveness_alert import (
    DocumentEffectivenessAlert,
)
from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


class DocumentEffectivenessAlertRepository(
    Protocol
):
    async def get_by_id(
        self,
        alert_id: UUID,
    ) -> (
        DocumentEffectivenessAlert
        | None
    ):
        ...

    async def get_list(
        self,
        status: (
            DocumentEffectivenessAlertStatus
            | None
        ),
        skip: int,
        limit: int,
    ) -> list[
        DocumentEffectivenessAlert
    ]:
        ...

    async def count(
        self,
        status: (
            DocumentEffectivenessAlertStatus
            | None
        ),
    ) -> int:
        ...

    async def add(
        self,
        alert: DocumentEffectivenessAlert,
    ) -> None:
        ...

    async def update(
        self,
        alert: DocumentEffectivenessAlert,
    ) -> None:
        ...