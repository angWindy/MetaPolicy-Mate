from pydantic import (
    BaseModel,
    Field,
)


class ApproveSectionMetadataRequest(
    BaseModel
):
    metadata: dict = Field(
        default_factory=dict
    )

    cross_references: list[
        dict
    ] = Field(
        default_factory=list
    )