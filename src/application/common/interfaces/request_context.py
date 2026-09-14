from typing import Protocol
from uuid import UUID

from src.domain.enums.audit_actor_type import (
    AuditActorType,
)


class RequestContext(Protocol):
    @property
    def user_id(self) -> UUID | None:
        ...

    @property
    def user_type(
        self,
    ) -> AuditActorType:
        ...

    @property
    def school_id(self) -> UUID | None:
        ...

    @property
    def school_code(self) -> str | None:
        ...

    @property
    def ip_address(self) -> str | None:
        ...

    @property
    def user_agent(self) -> str | None:
        ...

    @property
    def device_id(self) -> str | None:
        ...

    @property
    def trace_id(self) -> str | None:
        ...