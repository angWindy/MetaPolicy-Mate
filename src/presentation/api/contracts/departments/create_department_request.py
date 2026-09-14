from pydantic import (
    BaseModel,
    Field,
)


class CreateDepartmentRequest(
    BaseModel
):
    code: str = Field(
        min_length=1,
        max_length=100,
    )

    name: str = Field(
        min_length=1,
        max_length=255,
    )