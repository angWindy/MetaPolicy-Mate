import asyncio
import sys

from config import get_settings
from persistence.tenant.repositories.sqlalchemy_permission_repository import (
    SqlAlchemyPermissionRepository,
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
        user_repository = SqlAlchemyUserRepository(
            session
        )

        permission_repository = (
            SqlAlchemyPermissionRepository(
                session
            )
        )

        user = await user_repository.get_by_email(
            "admin@p234.demo"
        )

        if user is None:
            raise RuntimeError(
                "Demo admin not found."
            )

        permissions = (
            await permission_repository
            .get_by_user_id(
                user.id
            )
        )

        print(
            "User:",
            user.email,
        )

        print()
        print("Permissions:")

        for permission in permissions:
            print(
                "-",
                permission.code,
            )

        print()
        print(
            "Total:",
            len(permissions),
        )

        expected = {
            "document.read",
            "document.upload",
            "document.update",
            "document.delete",
            "chat.use",
            "user.read",
            "user.manage",
        }

        actual = {
            permission.code
            for permission in permissions
        }

        if actual != expected:
            raise RuntimeError(
                f"Permission mismatch: {actual}"
            )

        print()
        print(
            "User permission repository test PASS"
        )

    finally:
        await session.close()
        await factory.dispose()


asyncio.run(main())