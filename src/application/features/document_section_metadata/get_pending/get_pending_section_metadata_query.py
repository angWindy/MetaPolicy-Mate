from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetPendingSectionMetadataQuery:
    document_id: UUID
    version_id: UUID