from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from src.domain.entities.user import User


@dataclass(frozen=True)
class UserItem:
    id: UUID
    email: str
    full_name: str

    department_id: UUID | None

    token_version: int
    is_active: bool

    created_at: datetime | None
    updated_at: datetime | None

    @staticmethod
    def from_entity(
        user: User,
    ) -> "UserItem":
        return UserItem(
            id=user.id,
            email=user.email,

            full_name=(
                user.full_name
            ),

            department_id=(
                user.department_id
            ),

            token_version=(
                user.token_version
            ),

            is_active=(
                user.is_active
            ),

            created_at=(
                user.created_at
            ),

            updated_at=(
                user.updated_at
            ),
        )