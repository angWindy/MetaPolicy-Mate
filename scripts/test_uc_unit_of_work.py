import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4

from config import get_settings
from domain.entities.role import Role
from persistence.tenant.repositories.sqlalchemy_role_repository import (
    SqlAlchemyRoleRepository,
)
from persistence.tenant.session_factory import TenantSessionFactory
from persistence.tenant.unit_of_work import SqlAlchemyUnitOfWork


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


TEST_ROLE_CODE = "TEST_UOW_ROLE"


async def main() -> None:
    settings = get_settings()

    session_factory = TenantSessionFactory()
    session = session_factory.create(
        settings.database_url
    )

    try:
        role_repository = SqlAlchemyRoleRepository(
            session
        )

        unit_of_work = SqlAlchemyUnitOfWork(
            session
        )

        existing = await role_repository.get_by_code(
            TEST_ROLE_CODE
        )

        if existing is not None:
            print(
                "Test role already exists:",
                existing.code,
            )
            return

        role = Role(
            id=uuid4(),
            code=TEST_ROLE_CODE,
            name="Unit Of Work Test Role",
            description="Temporary integration test role",
            is_system=False,
            created_at=datetime.now(timezone.utc),
        )

        await role_repository.add(
            role
        )

        print(
            "Added to session:",
            role.code,
        )

        await unit_of_work.save_changes()

        print(
            "Committed:",
            role.code,
        )

    finally:
        await session.close()

    verify_session = session_factory.create(
        settings.database_url
    )

    try:
        verify_repository = SqlAlchemyRoleRepository(
            verify_session
        )

        saved_role = await verify_repository.get_by_code(
            TEST_ROLE_CODE
        )

        if saved_role is None:
            raise RuntimeError(
                "UnitOfWork commit failed"
            )

        print()
        print("VERIFY")
        print("ID:", saved_role.id)
        print("Code:", saved_role.code)
        print("Name:", saved_role.name)

    finally:
        await verify_session.close()
        await session_factory.dispose()


asyncio.run(main())