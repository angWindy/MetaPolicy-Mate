from dataclasses import (
    dataclass,
    field,
)
from datetime import date
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


@dataclass
class UpdateRegulatoryDocumentCommand:
    document_id: UUID

    document_number: str
    title: str
    issued_by: str

    issued_date: date
    effective_date: date

    # None nghĩa là chỉ sửa metadata,
    # giữ nguyên legal_status.
    legal_status: (
        DocumentLegalStatus | None
    ) = None

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
    ) -> UUID:
        return self.document_id

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
            "document_id":
                self.document_id,

            "document_number":
                self.document_number.strip(),

            "title":
                self.title.strip(),

            "issued_by":
                self.issued_by.strip(),

            "issued_date":
                self.issued_date,

            "effective_date":
                self.effective_date,

            # Bắt buộc có trong audit after.
            "legal_status": (
                self.legal_status.value
                if self.legal_status
                is not None
                else None
            ),
        }