from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateDepartmentCommand:
    department_id: str
    name: str | None = None
    is_active: bool | None = None
