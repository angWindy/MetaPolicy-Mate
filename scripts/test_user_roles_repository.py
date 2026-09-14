import asyncio
import sys

from config import get_settings
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

        user = (
            await user_repository.get_by_email(
                "admin@p234.demo"
            )
        )

        if user is None:
            raise RuntimeError(
                "Demo admin not found"
            )

        roles = (
            await role_repository.get_by_user_id(
                user.id
            )
        )

        print(
            "User:",
            user.email,
        )

        print()
        print("Roles:")

        for role in roles:
            print(
                "-",
                role.code,
            )

        print()
        print(
            "Total:",
            len(roles),
        )

        if len(roles) != 1:
            raise RuntimeError(
                "Expected exactly 1 role"
            )

        if roles[0].code != "ADMIN":
            raise RuntimeError(
                "Expected ADMIN role"
            )

        print()
        print(
            "User role repository test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())