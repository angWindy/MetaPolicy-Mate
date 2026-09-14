from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UserResponse(
    BaseModel
):
    id: UUID

    email: str
    full_name: str

    department_id: UUID | None

    token_version: int
    is_active: bool

    created_at: datetime | None
    updated_at: datetime | None