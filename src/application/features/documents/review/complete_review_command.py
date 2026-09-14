from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CompleteReviewCommand:
    version_id: UUID
    reviewer_id: UUID
    notes: str | None
