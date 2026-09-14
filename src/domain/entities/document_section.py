from dataclasses import dataclass
from uuid import UUID


@dataclass
class DocumentSection:
    id: UUID

    version_id: UUID

    section_type: str | None
    section_number: str | None
    heading: str | None

    heading_path: list[str]

    content: str

    page: int | None

    sort_order: int