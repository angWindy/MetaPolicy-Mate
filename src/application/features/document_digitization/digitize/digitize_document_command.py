from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from src.domain.enums.audit_action import (
    AuditAction,
)
from src.domain.enums.audit_entity import (
    AuditEntity,
)


@dataclass(frozen=True)
class DigitizeDocumentCommand:
    document_id: UUID
    version_id: UUID
    # Optional override for the OCR engine. Defaults to "rapidocr_vi"
    # (RapidOCR + PP-OCRv6 Vietnamese ONNX). Set to "pp_structure"
    # to enable the PP-StructureV3 layout-aware pipeline instead.
    ocr_engine: Literal["rapidocr_vi", "pp_structure"] = "rapidocr_vi"

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

    def get_payload(
        self,
    ) -> object:
        return {
            "operation":
                "document_digitized",

            "document_id":
                self.document_id,

            "version_id":
                self.version_id,
        }