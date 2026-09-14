import asyncio
import sys

from config import get_settings

from persistence.tenant.repositories.sqlalchemy_permission_repository import (
    SqlAlchemyPermissionRepository,
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


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    settings = get_settings()

    session_factory = TenantSessionFactory()

    session = session_factory.create(
        settings.database_url
    )

    try:
        user_repository = SqlAlchemyUserRepository(
            session
        )

        role_repository = SqlAlchemyRoleRepository(
            session
        )

        permission_repository = (
            SqlAlchemyPermissionRepository(
                session
            )
        )

        refresh_token_repository = (
            SqlAlchemyRefreshTokenRepository(
                session
            )
        )

        # 1. Test UserRepository
        user = await user_repository.get_by_email(
            "admin@p234.demo"
        )

        if user is None:
            raise RuntimeError(
                "Demo admin was not found"
            )

        print("USER")
        print("ID:", user.id)
        print("Email:", user.email)
        print("Name:", user.full_name)
        print("Active:", user.is_active)

        # 2. Test RoleRepository
        role = await role_repository.get_by_code(
            "ADMIN"
        )

        if role is None:
            raise RuntimeError(
                "ADMIN role was not found"
            )

        print()
        print("ROLE")
        print("ID:", role.id)
        print("Code:", role.code)
        print("Name:", role.name)

        # 3. Test PermissionRepository
        permissions = (
            await permission_repository.get_all()
        )

        print()
        print("PERMISSIONS")

        for permission in permissions:
            print(
                "-",
                permission.code,
            )

        print(
            "Total:",
            len(permissions),
        )

        # 4. Test RefreshTokenRepository
        refresh_token = (
            await refresh_token_repository.get_by_hash(
                "not-existing-token"
            )
        )

        print()
        print("REFRESH TOKEN")
        print(
            "Missing token result:",
            refresh_token,
        )

    finally:
        await session.close()
        await session_factory.dispose()


asyncio.run(main())