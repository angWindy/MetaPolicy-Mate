import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import get_settings


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


async def main() -> None:
    engine = create_async_engine(
        get_settings().database_url
    )

    try:
        async with engine.connect() as connection:
            for table in [
                "roles",
                "permissions",
                "role_permissions",
                "users",
                "user_roles",
            ]:
                result = await connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table}"
                    )
                )

                print(
                    f"{table}:",
                    result.scalar_one(),
                )

            result = await connection.execute(
                text(
                    """
                    SELECT
                        u.email,
                        u.full_name,
                        r.code
                    FROM users u
                    JOIN user_roles ur
                        ON ur.user_id = u.id
                    JOIN roles r
                        ON r.id = ur.role_id
                    ORDER BY u.email, r.code
                    """
                )
            )

            print("\nUsers / Roles:")

            for row in result:
                print(
                    row.email,
                    "|",
                    row.full_name,
                    "|",
                    row.code,
                )

    finally:
        await engine.dispose()


asyncio.run(main())