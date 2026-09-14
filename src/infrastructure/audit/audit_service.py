import json
from datetime import (
    datetime,
    timezone,
)
from uuid import uuid4

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.application.common.interfaces.audit_service import (
    AuditService as AuditServiceProtocol,
)
from src.domain.audit.audit_event import (
    AuditEvent,
)
from src.persistence.tenant.configurations.audit_outbox_configuration import (
    audit_outbox,
)


class AuditService(
    AuditServiceProtocol
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def emit(
        self,
        audit_event: AuditEvent,
    ) -> None:
        payload = json.dumps(
            audit_event,
            default=self._json_default,
            separators=(",", ":"),
        )

        try:
            await self._session.execute(
                insert(
                    audit_outbox
                ).values(
                    id=uuid4(),
                    event_type=(
                        "audit.event"
                    ),
                    payload=payload,
                    status="Pending",
                    retry_count=0,
                    created_at=(
                        datetime.now(
                            timezone.utc
                        )
                    ),
                    processed_at=None,
                    error=None,
                )
            )

            await self._session.commit()

        except Exception:
            await self._session.rollback()
            raise

    @staticmethod
    def _json_default(
        value: object,
    ):
        if hasattr(value, "value"):
            return value.value

        if hasattr(value, "__dict__"):
            return value.__dict__

        return str(value)