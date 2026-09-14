from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetRoleQuery:
    role_id: UUID