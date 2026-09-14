from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr

    password: str = Field(
        min_length=1,
    )

    device_id: str = Field(
        min_length=1,
    )