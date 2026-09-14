from pydantic import BaseModel, Field


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1,
    )

    device_id: str = Field(
        min_length=1,
    )