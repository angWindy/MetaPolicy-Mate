from typing import Protocol


class RefreshTokenService(Protocol):
    def generate_token(self) -> str:
        ...

    def hash_token(
        self,
        token: str,
    ) -> str:
        ...