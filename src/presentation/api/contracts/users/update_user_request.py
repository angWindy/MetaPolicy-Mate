from uuid import UUID

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


class UpdateUserRequest(
    BaseModel
):
    email: EmailStr

    full_name: str = Field(
        min_length=1,
        max_length=255,
    )

    department_id: UUID | None = None