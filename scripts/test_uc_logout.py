import asyncio
import sys

from application.common.exceptions.unauthorized_exception import (
    UnauthorizedException,
)
from application.features.auth.login.login_command import (
    LoginCommand,
)
from application.features.auth.login.login_handler import (
    LoginHandler,
)
from application.features.auth.logout.logout_command import (
    LogoutCommand,
)
from application.features.auth.logout.logout_handler import (
    LogoutHandler,
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

        login_handler = LoginHandler(
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

        logout_handler = LogoutHandler(
            refresh_token_repository=(
                refresh_token_repository
            ),
            refresh_token_service=(
                refresh_token_service
            ),
            unit_of_work=unit_of_work,
        )

        login_result = (
            await login_handler.handle(
                LoginCommand(
                    email="admin@p234.demo",
                    password="P234@123",
                    device_id=(
                        "logout-test-device"
                    ),
                )
            )
        )

        raw_refresh_token = (
            login_result.refresh_token
        )

        token_hash = (
            refresh_token_service.hash_token(
                raw_refresh_token
            )
        )

        token_before = (
            await refresh_token_repository
            .get_by_hash(
                token_hash
            )
        )

        if token_before is None:
            raise RuntimeError(
                "Refresh token was not stored."
            )

        print("BEFORE LOGOUT")
        print(
            "ID:",
            token_before.id,
        )
        print(
            "Revoked:",
            token_before.revoked_at,
        )

        await logout_handler.handle(
            LogoutCommand(
                refresh_token=(
                    raw_refresh_token
                )
            )
        )

        token_after = (
            await refresh_token_repository
            .get_by_hash(
                token_hash
            )
        )

        if token_after is None:
            raise RuntimeError(
                "Refresh token missing after logout."
            )

        print()
        print("AFTER LOGOUT")
        print(
            "Revoked:",
            token_after.revoked_at
            is not None,
        )

        if token_after.revoked_at is None:
            raise RuntimeError(
                "Refresh token was not revoked."
            )

        print()
        print("REUSE TOKEN")

        try:
            await logout_handler.handle(
                LogoutCommand(
                    refresh_token=(
                        raw_refresh_token
                    )
                )
            )
        except UnauthorizedException:
            print(
                "Revoked token rejected: True"
            )
        else:
            raise RuntimeError(
                "Revoked token was accepted."
            )

        print()
        print(
            "Logout integration test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())