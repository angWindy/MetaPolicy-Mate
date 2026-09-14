from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetFlaggedAnswersQuery:
    page: int = 1
    page_size: int = 20

    department_id: (
        UUID | None
    ) = None