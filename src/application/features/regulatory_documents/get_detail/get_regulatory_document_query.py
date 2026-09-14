from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetRegulatoryDocumentQuery:
    document_id: UUID