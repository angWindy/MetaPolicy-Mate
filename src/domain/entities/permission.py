from dataclasses import dataclass
from uuid import UUID


@dataclass
class Permission:
    id: UUID
    code: str
    name: str
    module: str

    description: str | None = None