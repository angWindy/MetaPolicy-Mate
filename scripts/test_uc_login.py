import asyncio
import sys

import jwt

from application.features.auth.login.login_command import (
    LoginCommand,
)
from application.features.auth.login.login_handler import (
    LoginHandler,
)
from config import get_settings
from infrastructure.auth.jwt_settings import (
    JwtSettings,
)
from infrastructure.auth.jwt_token_service import (
    JwtTokenService,
)
from infrastructure.auth.refresh_token_service import (
    RefreshTokenService,
)
from infrastructure.security.password_hasher import (
    PasswordHasher,
)
from persistence.tenant.repositories.sqlalchemy_refresh_token_repository import (
    SqlAlchemyRefreshTokenRepository,
)
from persistence.tenant.repositories.sqlalchemy_role_repository import (
    SqlAlchemyRoleRepository,
)
from persistence.tenant.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from persistence.tenant.session_factory import (
    TenantSessionFactory,
)
from persistence.tenant.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    settings = get_settings()

    factory = TenantSessionFactory()

    session = factory.create(
        settings.database_url
    )

    try:
        user_repository = (
            SqlAlchemyUserRepository(
                session
            )
        )

        role_repository = (
            SqlAlchemyRoleRepository(
                session
            )
        )

        refresh_token_repository = (
            SqlAlchemyRefreshTokenRepository(
                session
            )
        )

        password_hasher = PasswordHasher()

        refresh_token_service = (
            RefreshTokenService()
        )

        jwt_settings = JwtSettings(
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            secret_key=settings.jwt_secret_key,
            access_token_minutes=(
                settings.jwt_access_token_minutes
            ),
            refresh_token_days=(
                settings.jwt_refresh_token_days
            ),
        )

        jwt_token_service = (
            JwtTokenService(
                jwt_settings
            )
        )

        unit_of_work = (
            SqlAlchemyUnitOfWork(
                session
            )
        )

        handler = LoginHandler(
            user_repository=user_repository,
            role_repository=role_repository,
            refresh_token_repository=(
                refresh_token_repository
            ),
            password_hasher=password_hasher,
            jwt_token_service=(
                jwt_token_service
            ),
            refresh_token_service=(
                refresh_token_service
            ),
            unit_of_work=unit_of_work,
            settings=settings,
        )

        command = LoginCommand(
            email="admin@p234.demo",
            password="P234@123",
            device_id="test-device-001",
        )

        result = await handler.handle(
            command
        )

        print("LOGIN")
        print(
            "Access token generated:",
            bool(result.access_token),
        )
        print(
            "Refresh token generated:",
            bool(result.refresh_token),
        )
        print(
            "Expires at:",
            result.expires_at,
        )

        claims = jwt.decode(
            result.access_token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )

        print()
        print("JWT")
        print(
            "sub:",
            claims.get("sub"),
        )
        print(
            "email:",
            claims.get("email"),
        )
        print(
            "role:",
            claims.get("role"),
        )
        print(
            "TokenVersion:",
            claims.get("TokenVersion"),
        )
        print(
            "userType:",
            claims.get("userType"),
        )
        print(
            "SchoolId:",
            claims.get("SchoolId"),
        )

        refresh_token_hash = (
            refresh_token_service.hash_token(
                result.refresh_token
            )
        )

        stored_refresh_token = (
            await refresh_token_repository
            .get_by_hash(
                refresh_token_hash
            )
        )

        print()
        print("REFRESH TOKEN DB")
        print(
            "Stored:",
            stored_refresh_token
            is not None,
        )

        if stored_refresh_token is None:
            raise RuntimeError(
                "Refresh token was not persisted."
            )

        print(
            "UserId:",
            stored_refresh_token.user_id,
        )
        print(
            "DeviceId:",
            stored_refresh_token.device_id,
        )
        print(
            "Revoked:",
            stored_refresh_token.revoked_at
            is not None,
        )

        assert (
            claims["email"]
            == "admin@p234.demo"
        )
        assert claims["role"] == "ADMIN"
        assert (
            claims["SchoolId"]
            == str(settings.school_id)
        )
        assert (
            stored_refresh_token.device_id
            == "test-device-001"
        )

        print()
        print(
            "Login integration test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())