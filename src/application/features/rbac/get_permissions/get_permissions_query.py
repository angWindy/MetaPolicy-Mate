from dataclasses import dataclass


@dataclass(frozen=True)
class GetPermissionsQuery:
    module: str | None = None