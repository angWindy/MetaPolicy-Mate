from datetime import datetime

from pydantic import BaseModel


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime