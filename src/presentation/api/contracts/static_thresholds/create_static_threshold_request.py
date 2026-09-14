from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
)


class CreateStaticThresholdRequest(
    BaseModel
):
    threshold_key: str = Field(
        min_length=1,
        max_length=150,
    )

    scope_key: str = Field(
        min_length=1,
        max_length=200,
    )

    name: str = Field(
        min_length=1,
        max_length=500,
    )

    operator: str = Field(
        min_length=1,
        max_length=10,
    )

    value: Decimal

    unit: str | None = Field(
        default=None,
        max_length=100,
    )

    condition_text: str = Field(
        min_length=1,
        max_length=4000,
    )

    section_id: UUID
    section_version_id: UUID