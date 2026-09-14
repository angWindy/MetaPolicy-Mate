from pydantic import (
    BaseModel,
    Field,
)


class ReviewAnswerRequest(
    BaseModel
):
    review_result: str = Field(
        min_length=1,
        max_length=30,
    )

    review_note: str | None = Field(
        default=None,
        max_length=4000,
    )