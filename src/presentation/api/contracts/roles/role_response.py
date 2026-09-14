from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RoleResponse(
    BaseModel
):
    id: UUID

    code: str
    name: str

    description: str | None

    is_system: bool

    created_at: datetime | None