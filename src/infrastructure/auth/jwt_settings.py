from dataclasses import dataclass

from src.application.common.interfaces.token_configuration import (
    TokenConfiguration,
)


@dataclass
class JwtSettings(TokenConfiguration):
    SECTION_NAME = "JwtSettings"

    issuer: str = ""
    audience: str = ""
    secret_key: str = ""
    access_token_minutes: int = 0
    refresh_token_days: int = 0