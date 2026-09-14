from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class LogoutAllCommand:
    user_id: UUID