from dataclasses import dataclass
from uuid import UUID

from src.domain.enums.audit_actor_type import (
    AuditActorType,
)


@dataclass(frozen=True)
class JwtUser:
    user_id: UUID
    school_id: UUID | None = None
    school_code: str = ""
    email: str = ""
    role: str = ""
    user_type: AuditActorType = (
        AuditActorType.PLATFORM_USER
    )
    token_version: int = 0