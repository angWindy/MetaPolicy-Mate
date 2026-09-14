from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RegisterResult:
    access_token: str
    refresh_token: str
    expires_at: datetime
    user_id: str
    email: str
    full_name: str
    role: str
    department: str | None
