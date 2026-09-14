from dataclasses import dataclass


@dataclass
class AuditContext:
    ip: str | None = None
    user_agent: str | None = None
    device_id: str | None = None
    trace_id: str | None = None