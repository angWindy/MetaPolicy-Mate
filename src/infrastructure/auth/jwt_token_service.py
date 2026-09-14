from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any
from uuid import uuid4

import jwt

from src.application.common.interfaces.jwt_token_service import (
    JwtTokenService as JwtTokenServiceProtocol,
)
from src.domain.auth.jwt_user import JwtUser
from src.infrastructure.auth.jwt_settings import (
    JwtSettings,
)


class JwtTokenService(
    JwtTokenServiceProtocol
):
    def __init__(
        self,
        jwt_settings: JwtSettings,
    ) -> None:
        self._jwt_settings = jwt_settings

    def generate_access_token(
        self,
        user: JwtUser,
    ) -> str:
        claims = {
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role,
            "TokenVersion": str(
                user.token_version
            ),
            "userType": str(
                user.user_type.value
            ),
            "SchoolId": (
                str(user.school_id)
                if user.school_id is not None
                else ""
            ),
            # New (2026-08): per-user ``SchoolCode`` claim resolved
            # from the user's bound department at login time. This is
            # the canonical source for tenant identity in
            # ``RequestContext.school_code`` — settings-based tenant
            # identity was removed because it leaked a hardcoded UUID
            # into every JWT and every R2 key.
            "SchoolCode": user.school_code or "",
            "jti": str(uuid4()),
            "iss": self._jwt_settings.issuer,
            "aud": self._jwt_settings.audience,
            "exp": (
                datetime.now(
                    timezone.utc
                )
                + timedelta(
                    minutes=(
                        self._jwt_settings
                        .access_token_minutes
                    )
                )
            ),
        }

        return jwt.encode(
            claims,
            self._jwt_settings.secret_key,
            algorithm="HS256",
        )

    def get_principal_from_expired_token(
        self,
        token: str,
    ) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._jwt_settings.secret_key,
            algorithms=["HS256"],
            options={
                "verify_exp": False,
                "verify_iss": False,
                "verify_aud": False,
            },
        )

    def validate_access_token(
        self,
        token: str,
    ) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._jwt_settings.secret_key,
            algorithms=["HS256"],
            issuer=self._jwt_settings.issuer,
            audience=self._jwt_settings.audience,
            options={
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )