from dataclasses import dataclass


@dataclass
class AuditData:
    before: object | None = None
    after: object | None = None
    extra: dict[str, object] | None = None