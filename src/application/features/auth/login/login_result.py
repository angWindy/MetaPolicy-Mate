from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class LoginResult:
    access_token: str
    refresh_token: str
    expires_at: datetime