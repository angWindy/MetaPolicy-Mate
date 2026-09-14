from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class DocumentSectionItem:
    id: UUID
    section_type: str | None
    section_number: str | None
    heading: str | None
    heading_path: list[str]
    page: int | None
    sort_order: int

    @staticmethod
    def from_domain(section) -> "DocumentSectionItem":
        heading_path: list[Any] = list(
            section.heading_path or []
        )
        # Some legacy rows store heading_path as a JSON string;
        # coerce to a list before returning to the FE.
        if (
            heading_path
            and isinstance(heading_path[0], str)
        ):
            try:
                import json

                parsed = json.loads(heading_path[0])
                if isinstance(parsed, list):
                    heading_path = [
                        str(item) for item in parsed
                    ]
            except (ValueError, TypeError):
                # leave as-is — the FE will display the raw value.
                pass

        return DocumentSectionItem(
            id=section.id,
            section_type=section.section_type,
            section_number=section.section_number,
            heading=section.heading,
            heading_path=[str(p) for p in heading_path],
            page=section.page,
            sort_order=section.sort_order,
        )
