from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetUserRolesQuery:
    user_id: UUID