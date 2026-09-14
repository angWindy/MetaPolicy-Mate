from pydantic import (
    BaseModel,
    Field,
)


class UpdateDepartmentRequest(
    BaseModel
):
    name: str = Field(
        min_length=1,
        max_length=255,
    )

    is_active: bool | None = Field(
        default=None,
    )
