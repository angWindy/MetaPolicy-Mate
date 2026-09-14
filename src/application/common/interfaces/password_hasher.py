from typing import Protocol


class PasswordHasher(Protocol):
    def hash_password(
        self,
        password: str,
    ) -> str:
        ...

    def verify_password(
        self,
        password: str,
        stored_hash: str,
    ) -> bool:
        ...