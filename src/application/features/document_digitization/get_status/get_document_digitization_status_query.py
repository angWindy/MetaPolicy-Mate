from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentDigitizationStatusQuery:
    document_id: UUID
    version_id: UUID