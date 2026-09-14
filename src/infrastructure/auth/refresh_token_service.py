import base64
import hashlib
import secrets

from src.application.common.interfaces.refresh_token_service import (
    RefreshTokenService as RefreshTokenServiceProtocol,
)


class RefreshTokenService(RefreshTokenServiceProtocol):
    def generate_token(self) -> str:
        random_bytes = secrets.token_bytes(64)

        return base64.b64encode(
            random_bytes
        ).decode("utf-8")

    def hash_token(
        self,
        token: str,
    ) -> str:
        token_bytes = token.encode("utf-8")

        token_hash = hashlib.sha256(
            token_bytes
        ).digest()

        return base64.b64encode(
            token_hash
        ).decode("utf-8")