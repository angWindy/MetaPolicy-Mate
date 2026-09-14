from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class RefreshToken:
    id: UUID
    user_id: UUID

    token_hash: str

    expires_at: datetime
    created_at: datetime

    device_id: str | None = None
    revoked_at: datetime | None = None

    replaced_by_token_id: UUID | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_active(self) -> bool:
        return (
            not self.is_revoked
            and self.expires_at > datetime.now(
                self.expires_at.tzinfo
            )
        )