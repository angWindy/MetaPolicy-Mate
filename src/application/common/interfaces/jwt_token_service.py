from typing import Any, Protocol

from src.domain.auth.jwt_user import JwtUser


class JwtTokenService(Protocol):
    def generate_access_token(
        self,
        user: JwtUser,
    ) -> str:
        ...

    def validate_access_token(
        self,
        token: str,
    ) -> dict[str, Any]:
        ...

    def get_principal_from_expired_token(
        self,
        token: str,
    ) -> dict[str, Any]:
        ...