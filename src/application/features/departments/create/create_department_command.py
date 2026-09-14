from dataclasses import dataclass


@dataclass(frozen=True)
class CreateDepartmentCommand:
    code: str
    name: str