"""AutoApproveReview command — admin fast-track approval for
documents that fail :class:`MetadataQualityGate` on first ingestion.

The metadata cleanup plan (2026-09-06) routes documents with missing
fields (hand-written document_number, OCR'd `issued_date`, etc.) into
``PENDING_REVIEW``. Admins then have two paths:

1. Edit the metadata manually via the admin UI; then click
   ``/complete-review`` and ``/approve`` to flip the status.
2. Click ``/auto-approve-metadata`` (this command): the handler re-runs
   :class:`MetadataQualityGate` against the current ``Document`` row;
   if it passes, the version transitions straight to
   ``ProcessingStatus.APPROVED`` and the admin can trigger
   ``/index`` to push to Qdrant.

Path 2 is meant for cases where the OCR pipeline already produced
good metadata but the gate failed because of a transient issue
(e.g. handler received a half-updated Document object) — i.e. the
gate passes on a re-read but the admin has not manually edited
anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AutoApproveReviewCommand:
    """Trigger a re-evaluation of the metadata gate.

    Attributes:
        version_id: target document version.
        admin_id: operator performing the action — recorded for audit.
        notes: free-text rationale shown in the admin queue.
    """

    version_id: UUID
    admin_id: UUID
    notes: str | None = None

    def to_audit_payload(self) -> dict[str, Any]:
        """JSON-safe projection used by audit-log decorators."""
        return {
            "operation": "metadata_auto_approved",
            "version_id": str(self.version_id),
            "admin_id": str(self.admin_id),
            "notes": self.notes,
        }
