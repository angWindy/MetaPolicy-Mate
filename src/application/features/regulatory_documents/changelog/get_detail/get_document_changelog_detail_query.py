from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentChangelogDetailQuery:
    document_id: UUID
    changelog_id: UUID