from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DocumentChangelogResponse(
    BaseModel
):
    id: UUID

    document_id: UUID

    action: str

    actor_id: UUID | None
    actor_type: str | None

    old_values: Any | None
    new_values: Any | None
    metadata: Any | None

    ip_address: str | None
    device_id: str | None
    user_agent: str | None

    created_at: datetime