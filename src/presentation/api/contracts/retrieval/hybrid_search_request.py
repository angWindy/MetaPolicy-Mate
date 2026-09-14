from datetime import date

from pydantic import (
    BaseModel,
    Field,
)


class HybridSearchRequest(
    BaseModel
):
    query: str = Field(
        min_length=1,
        max_length=2000,
    )

    as_of_date: date | None = None