from dataclasses import dataclass
from datetime import date

from src.domain.enums.audit_action import AuditAction
from src.domain.enums.audit_entity import AuditEntity


@dataclass(frozen=True)
class UploadRegulatoryDocumentCommand:
    document_number: str
    title: str
    issued_by: str

    issued_date: date
    effective_date: date

    source_filename: str
    content_type: str
    content: bytes

    # Phase 5: when True, the upload handler kicks off the RAG
    # digitization pipeline (parse -> chunk -> embed -> Qdrant
    # upsert) after persisting the document. Defaults to False to
    # keep upload-only behaviour for callers that don't need
    # auto-indexing (Phase 3 contract).
    auto_digitize: bool = False

    @property
    def action(self) -> AuditAction:
        return AuditAction.CREATE

    @property
    def entity(self) -> AuditEntity:
        return AuditEntity.REGULATORY_DOCUMENT

    @property
    def entity_id(self):
        return None

    def get_payload(self) -> object:
        return {
            "document_number": self.document_number,
            "title": self.title,
            "issued_by": self.issued_by,
            "issued_date": self.issued_date,
            "effective_date": self.effective_date,
            "source_filename": self.source_filename,
            "content_type": self.content_type,
            "size_bytes": len(self.content),
            "auto_digitize": self.auto_digitize,
        }