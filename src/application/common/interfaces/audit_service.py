from typing import Protocol

from src.domain.audit.audit_event import AuditEvent


class AuditService(Protocol):
    async def emit(
        self,
        audit_event: AuditEvent,
    ) -> None:
        ...