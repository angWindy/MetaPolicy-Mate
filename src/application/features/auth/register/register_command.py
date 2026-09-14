from dataclasses import dataclass


@dataclass(frozen=True)
class RegisterCommand:
    email: str
    password: str
    full_name: str
    school_code: str
