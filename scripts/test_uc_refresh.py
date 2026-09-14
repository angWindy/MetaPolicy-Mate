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
from application.features.auth.refresh.refresh_command import (
    RefreshCommand,
)
from application.features.auth.refresh.refresh_handler import (
    RefreshHandler,
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
from persistence.tenant.repositories.sqlalchemy_department_repository import (
    SqlAlchemyDepartmentRepository,
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
        user_repository = SqlAlchemyUserRepository(
            session
        )

        role_repository = SqlAlchemyRoleRepository(
            session
        )

        department_repository = SqlAlchemyDepartmentRepository(
            session
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

        jwt_token_service = JwtTokenService(
            jwt_settings
        )

        unit_of_work = SqlAlchemyUnitOfWork(
            session
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

        refresh_handler = RefreshHandler(
            user_repository=user_repository,
            role_repository=role_repository,
            department_repository=(
                department_repository
            ),
            refresh_token_repository=(
                refresh_token_repository
            ),
            jwt_token_service=(
                jwt_token_service
            ),
            refresh_token_service=(
                refresh_token_service
            ),
            unit_of_work=unit_of_work,
            settings=settings,
        )

        login_result = (
            await login_handler.handle(
                LoginCommand(
                    email="admin@p234.demo",
                    password="P234@123",
                    device_id=(
                        "refresh-test-device"
                    ),
                )
            )
        )

        old_raw_token = (
            login_result.refresh_token
        )

        old_hash = (
            refresh_token_service.hash_token(
                old_raw_token
            )
        )

        old_token_before = (
            await refresh_token_repository
            .get_by_hash(
                old_hash
            )
        )

        if old_token_before is None:
            raise RuntimeError(
                "Old refresh token "
                "was not stored."
            )

        print("OLD TOKEN")
        print(
            "ID:",
            old_token_before.id,
        )
        print(
            "Revoked:",
            old_token_before.revoked_at,
        )

        refresh_result = (
            await refresh_handler.handle(
                RefreshCommand(
                    refresh_token=old_raw_token,
                    device_id=(
                        "refresh-test-device"
                    ),
                )
            )
        )

        print()
        print("REFRESH")
        print(
            "Access token generated:",
            bool(
                refresh_result.access_token
            ),
        )
        print(
            "New refresh token generated:",
            bool(
                refresh_result.refresh_token
            ),
        )

        new_hash = (
            refresh_token_service.hash_token(
                refresh_result.refresh_token
            )
        )

        old_token_after = (
            await refresh_token_repository
            .get_by_hash(
                old_hash
            )
        )

        new_token = (
            await refresh_token_repository
            .get_by_hash(
                new_hash
            )
        )

        if old_token_after is None:
            raise RuntimeError(
                "Old token missing."
            )

        if new_token is None:
            raise RuntimeError(
                "New token missing."
            )

        print()
        print("ROTATION")
        print(
            "Old revoked:",
            old_token_after.revoked_at
            is not None,
        )
        print(
            "Old replaced by:",
            old_token_after
            .replaced_by_token_id,
        )
        print(
            "New ID:",
            new_token.id,
        )
        print(
            "New revoked:",
            new_token.revoked_at
            is not None,
        )

        if old_token_after.revoked_at is None:
            raise RuntimeError(
                "Old token was not revoked."
            )

        if (
            old_token_after
            .replaced_by_token_id
            != new_token.id
        ):
            raise RuntimeError(
                "Rotation chain mismatch."
            )

        if new_token.revoked_at is not None:
            raise RuntimeError(
                "New token should be active."
            )

        print()
        print("REUSE OLD TOKEN")

        try:
            await refresh_handler.handle(
                RefreshCommand(
                    refresh_token=(
                        old_raw_token
                    ),
                    device_id=(
                        "refresh-test-device"
                    ),
                )
            )
        except UnauthorizedException:
            print(
                "Old token rejected: True"
            )
        else:
            raise RuntimeError(
                "Revoked old token "
                "was accepted."
            )

        print()
        print(
            "Refresh rotation "
            "integration test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())