from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class User:
    id: UUID
    email: str
    password_hash: str
    full_name: str

    department_id: UUID | None = None

    is_admin: bool = False

    token_version: int = 0
    is_active: bool = True

    created_at: datetime | None = None
    updated_at: datetime | None = None