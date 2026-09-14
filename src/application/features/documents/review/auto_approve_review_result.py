"""AutoApproveReview result — typed return of the auto-approve flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.domain.schemas import ProcessingStatus


@dataclass(frozen=True)
class AutoApproveReviewResult:
    """Outcome of an auto-approve review attempt.

    Attributes:
        version_id: target version (echoed for callers).
        status: status the version was flipped to — ``APPROVED`` on
            success, ``PENDING_REVIEW`` if the gate still fails.
        validation_result: JSON projection of
            :class:`src.application.common.metadata_quality_gate.
            MetadataQualityResult` so the admin UI can render the
            remaining fix list without re-querying the gate.
        approved_at: wall-clock time the transition was committed
            (``None`` if the gate still fails).
    """

    version_id: UUID
    status: ProcessingStatus
    validation_result: dict[str, Any]
    approved_at: datetime | None = None

    @property
    def auto_approved(self) -> bool:
        """True iff the gate passed and the version moved to ``APPROVED``."""
        return self.status == ProcessingStatus.APPROVED
