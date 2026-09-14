from dataclasses import dataclass

from src.application.common.document_access_policy import (
    can_access_document,
)
from src.application.common.pipeline.interfaces.request_handler import (
    RequestHandler,
)
from src.application.features.document_effectiveness_alerts.common.document_effectiveness_alert_item import (
    DocumentEffectivenessAlertItem,
)
from src.application.features.document_effectiveness_alerts.get_list.get_document_effectiveness_alerts_query import (
    GetDocumentEffectivenessAlertsQuery,
)
from src.domain.repositories.document_department_repository import (
    DocumentDepartmentRepository,
)
from src.domain.repositories.document_effectiveness_alert_repository import (
    DocumentEffectivenessAlertRepository,
)
from src.domain.repositories.document_repository import (
    DocumentRepository,
)


@dataclass(frozen=True)
class DocumentEffectivenessAlertListResult:
    items: list[
        DocumentEffectivenessAlertItem
    ]

    total: int
    page: int
    page_size: int


class GetDocumentEffectivenessAlertsHandler(
    RequestHandler[
        GetDocumentEffectivenessAlertsQuery,
        DocumentEffectivenessAlertListResult,
    ]
):
    _SCAN_SIZE = 100

    def __init__(
        self,
        alert_repository: (
            DocumentEffectivenessAlertRepository
        ),
        document_repository: (
            DocumentRepository
        ),
        document_department_repository: (
            DocumentDepartmentRepository
        ),
    ) -> None:
        self._alert_repository = (
            alert_repository
        )

        self._document_repository = (
            document_repository
        )

        self._document_department_repository = (
            document_department_repository
        )

    async def handle(
        self,
        request: (
            GetDocumentEffectivenessAlertsQuery
        ),
    ) -> (
        DocumentEffectivenessAlertListResult
    ):
        raw_total = await (
            self._alert_repository.count(
                status=request.status
            )
        )

        allowed_items: list[
            DocumentEffectivenessAlertItem
        ] = []

        offset = 0

        while offset < raw_total:
            alerts = await (
                self._alert_repository
                .get_list(
                    status=request.status,
                    skip=offset,
                    limit=self._SCAN_SIZE,
                )
            )

            if not alerts:
                break

            for alert in alerts:
                allowed = await (
                    can_access_document(
                        document_id=(
                            alert
                            .affected_document_id
                        ),
                        department_id=(
                            request.department_id
                        ),
                        document_repository=(
                            self
                            ._document_repository
                        ),
                        document_department_repository=(
                            self
                            ._document_department_repository
                        ),
                    )
                )

                if not allowed:
                    continue

                allowed_items.append(
                    DocumentEffectivenessAlertItem
                    .from_entity(
                        alert
                    )
                )

            offset += len(
                alerts
            )

        page_start = (
            request.page - 1
        ) * request.page_size

        page_end = (
            page_start
            + request.page_size
        )

        page_items = (
            allowed_items[
                page_start:page_end
            ]
        )

        return (
            DocumentEffectivenessAlertListResult(
                items=page_items,
                total=len(
                    allowed_items
                ),
                page=request.page,
                page_size=(
                    request.page_size
                ),
            )
        )