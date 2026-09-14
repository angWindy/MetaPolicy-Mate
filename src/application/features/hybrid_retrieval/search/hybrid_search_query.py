from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class HybridSearchQuery:
    query: str

    user_id: UUID

    department_id: UUID | None

    department: str

    roles: set[str]

    as_of_date: date | None = None