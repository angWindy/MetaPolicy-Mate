import asyncio
import sys

from config import get_settings
from domain.auth.jwt_user import JwtUser
from domain.enums.audit_actor_type import AuditActorType
from infrastructure.auth.jwt_settings import JwtSettings
from infrastructure.auth.jwt_token_service import JwtTokenService
from infrastructure.auth.refresh_token_service import RefreshTokenService
from infrastructure.security.password_hasher import PasswordHasher
from persistence.tenant.repositories.sqlalchemy_user_repository import (
    SqlAlchemyUserRepository,
)
from persistence.tenant.session_factory import TenantSessionFactory


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
        # ==========================================
        # 1. PasswordHasher + password thật trong DB
        # ==========================================

        user_repository = SqlAlchemyUserRepository(
            session
        )

        user = await user_repository.get_by_email(
            "admin@p234.demo"
        )

        if user is None:
            raise RuntimeError(
                "Demo admin not found"
            )

        password_hasher = PasswordHasher()

        password_valid = (
            password_hasher.verify_password(
                "P234@123",
                user.password_hash,
            )
        )

        print("PASSWORD")
        print("Valid:", password_valid)

        if not password_valid:
            raise RuntimeError(
                "Password verification failed"
            )

        # ==========================================
        # 2. JWT
        # ==========================================

        jwt_settings = JwtSettings(
            issuer="p234",
            audience="p234-client",
            secret_key=(
                "test-secret-key-for-p234-"
                "integration-test-only"
            ),
            access_token_minutes=30,
            refresh_token_days=7,
        )

        jwt_service = JwtTokenService(
            jwt_settings
        )

        jwt_user = JwtUser(
            user_id=user.id,
            school_id=None,
            email=user.email,
            role="ADMIN",
            user_type=AuditActorType.SCHOOL_USER,
            token_version=user.token_version,
        )

        access_token = (
            jwt_service.generate_access_token(
                jwt_user
            )
        )

        claims = (
            jwt_service
            .get_principal_from_expired_token(
                access_token
            )
        )

        print()
        print("JWT")
        print("Generated:", bool(access_token))
        print("sub:", claims["sub"])
        print("email:", claims["email"])
        print("role:", claims["role"])
        print(
            "TokenVersion:",
            claims["TokenVersion"],
        )

        if claims["sub"] != str(user.id):
            raise RuntimeError(
                "JWT sub mismatch"
            )

        if claims["email"] != user.email:
            raise RuntimeError(
                "JWT email mismatch"
            )

        if claims["TokenVersion"] != str(
            user.token_version
        ):
            raise RuntimeError(
                "JWT token version mismatch"
            )

        # ==========================================
        # 3. RefreshTokenService
        # ==========================================

        refresh_service = RefreshTokenService()

        refresh_token = (
            refresh_service.generate_token()
        )

        hash_1 = refresh_service.hash_token(
            refresh_token
        )

        hash_2 = refresh_service.hash_token(
            refresh_token
        )

        print()
        print("REFRESH TOKEN")
        print(
            "Generated:",
            bool(refresh_token),
        )
        print(
            "Hash generated:",
            bool(hash_1),
        )
        print(
            "Hash deterministic:",
            hash_1 == hash_2,
        )

        if hash_1 != hash_2:
            raise RuntimeError(
                "Refresh token hash mismatch"
            )

        print()
        print(
            "Auth service integration test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())