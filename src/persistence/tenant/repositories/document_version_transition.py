from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.schemas import ProcessingStatus
from src.persistence.tenant.models.document_version import (
    DocumentVersionModel,
)


class DocumentVersionTransition:
    """Helper to perform strict state transitions on document versions.

    Uses raw SQL for simplicity (we are deliberately NOT going through the
    full domain entity/repository round-trip here because the admin
    router already does session management and we just need to enforce
    the new gate ``PENDING_APPROVAL -> APPROVED``).
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def get_status(
        self,
        version_id,
    ) -> str | None:
        result = await self._session.execute(
            select(DocumentVersionModel.processing_status).where(
                DocumentVersionModel.id == version_id,
            )
        )
        return result.scalar_one_or_none()

    async def approve(
        self,
        version_id,
    ) -> datetime | None:
        """Move PENDING_APPROVAL → APPROVED. Returns approved_at."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            DocumentVersionModel.__table__.update()
            .where(
                DocumentVersionModel.id == version_id,
                DocumentVersionModel.processing_status
                == ProcessingStatus.PENDING_APPROVAL.value,
            )
            .values(
                processing_status=ProcessingStatus.APPROVED.value,
                approved_at=now,
            )
        )
        if result.rowcount == 0:
            return None
        return now
