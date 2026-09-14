from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.domain.entities.static_threshold import (
    StaticThreshold,
)


@dataclass(frozen=True)
class StaticThresholdDto:
    id: UUID

    threshold_key: str
    scope_key: str

    version_number: int

    name: str

    operator: str
    value: Decimal

    unit: str | None

    condition_text: str

    section_id: UUID
    section_version_id: UUID

    status: str
    is_current: bool

    verified_at: datetime | None

    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def from_entity(
        cls,
        item: StaticThreshold,
    ) -> "StaticThresholdDto":
        return cls(
            id=item.id,
            threshold_key=(
                item.threshold_key
            ),
            scope_key=(
                item.scope_key
            ),
            version_number=(
                item.version_number
            ),
            name=item.name,
            operator=item.operator,
            value=item.value,
            unit=item.unit,
            condition_text=(
                item.condition_text
            ),
            section_id=(
                item.section_id
            ),
            section_version_id=(
                item.section_version_id
            ),
            status=item.status.value,
            is_current=(
                item.is_current
            ),
            verified_at=(
                item.verified_at
            ),
            created_at=(
                item.created_at
            ),
            updated_at=(
                item.updated_at
            ),
        )