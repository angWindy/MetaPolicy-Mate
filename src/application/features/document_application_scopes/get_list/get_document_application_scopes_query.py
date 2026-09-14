from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentApplicationScopesQuery:
    document_id: UUID