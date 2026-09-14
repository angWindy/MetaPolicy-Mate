from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetUserPermissionsQuery:
    user_id: UUID