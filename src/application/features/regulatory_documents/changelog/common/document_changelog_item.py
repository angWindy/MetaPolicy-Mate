from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.entities.document_changelog_entry import (
    DocumentChangelogEntry,
)


@dataclass(frozen=True)
class DocumentChangelogItem:
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

    @staticmethod
    def from_entity(
        entity: DocumentChangelogEntry,
    ) -> "DocumentChangelogItem":
        return DocumentChangelogItem(
            id=entity.id,

            document_id=(
                entity.document_id
            ),

            action=entity.action,

            actor_id=(
                entity.actor_id
            ),

            actor_type=(
                entity.actor_type
            ),

            old_values=(
                entity.old_values
            ),

            new_values=(
                entity.new_values
            ),

            metadata=(
                entity.metadata
            ),

            ip_address=(
                entity.ip_address
            ),

            device_id=(
                entity.device_id
            ),

            user_agent=(
                entity.user_agent
            ),

            created_at=(
                entity.created_at
            ),
        )