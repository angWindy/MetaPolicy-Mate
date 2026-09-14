from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class GetDocumentsDueForEffectivenessQuery:
    as_of: date

    department_id: UUID | None = None