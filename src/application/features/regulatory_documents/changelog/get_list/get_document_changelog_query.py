from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentChangelogQuery:
    document_id: UUID

    action: str | None = None

    from_at: datetime | None = None
    to_at: datetime | None = None

    page: int = 1
    page_size: int = 20