from dataclasses import (
    dataclass,
    field,
)
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)
from src.domain.enums.document_effectiveness_alert_status import (
    DocumentEffectivenessAlertStatus,
)


@dataclass
class UpdateDocumentEffectivenessAlertStatusCommand:
    alert_id: UUID

    status: (
        DocumentEffectivenessAlertStatus
    )

    _audit_before: object | None = field(
        default=None,
        init=False,
        repr=False,
    )

    @property
    def action(
        self,
    ) -> AuditAction:
        return AuditAction.UPDATE

    @property
    def entity(
        self,
    ) -> AuditEntity:
        return (
            AuditEntity
            .REGULATORY_DOCUMENT
        )

    @property
    def entity_id(
        self,
    ) -> UUID | None:
        # alert_id không phải document_id.
        # Decorator resolve ID thật từ response.
        return None

    def get_audit_entity_id(
        self,
        response,
    ) -> UUID | None:
        return getattr(
            response,
            "affected_document_id",
            None,
        )

    def set_audit_before(
        self,
        value: object,
    ) -> None:
        self._audit_before = value

    def get_audit_before(
        self,
    ) -> object | None:
        return self._audit_before

    def get_payload(
        self,
    ) -> object:
        return {
            "alert_id":
                self.alert_id,
            "status":
                self.status.value,
            "operation":
                "effectiveness_alert_status_updated",
        }