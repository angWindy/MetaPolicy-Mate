from datetime import datetime

from pydantic import BaseModel


class RegisterResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str
    email: str
    full_name: str
    role: str
    department: str | None
