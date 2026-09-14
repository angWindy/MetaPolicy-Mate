from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from src.domain.enums.static_threshold_status import (
    StaticThresholdStatus,
)


@dataclass
class StaticThreshold:
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

    status: StaticThresholdStatus

    is_current: bool

    verified_at: datetime | None

    created_at: datetime
    updated_at: datetime | None