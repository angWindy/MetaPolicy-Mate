from dataclasses import dataclass
from uuid import UUID


@dataclass
class DocumentChunk:
    id: UUID

    version_id: UUID
    section_id: UUID | None

    chunk_index: int

    text: str
    embedding_text: str

    content_hash: str

    metadata: dict