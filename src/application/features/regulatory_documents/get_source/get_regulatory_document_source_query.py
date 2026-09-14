from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetRegulatoryDocumentSourceResult:
    content: bytes

    source_filename: str
    content_type: str


@dataclass(frozen=True)
class GetRegulatoryDocumentSourceQuery:
    document_id: UUID