from uuid import UUID

from pydantic import BaseModel


class DocumentSectionResponse(BaseModel):
    id: UUID
    section_type: str | None = None
    section_number: str | None = None
    heading: str | None = None
    heading_path: list[str] = []
    page: int | None = None
    sort_order: int
