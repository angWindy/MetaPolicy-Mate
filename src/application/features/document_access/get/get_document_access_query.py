from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentAccessQuery:
    document_id: UUID