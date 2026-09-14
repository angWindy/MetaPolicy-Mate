"""
Seed script to create demo users for multi-school access testing.

Creates 3 users:
1. HUCE User - can only access documents with HUCE department
2. HUST User - can only access documents with HUST department
3. Cross-School User - can access documents from any school (department = "*")
"""

import asyncio
import sys
from uuid import UUID, uuid4

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import get_settings

# Demo user UUIDs are derived from a stable namespace via UUIDv5 so the
# same email always resolves to the same ID across runs. See
# ``scripts/_seed_ids.py`` for the stability contract.
from scripts._seed_ids import seed_user_id


if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy()
    )


# User IDs are derived from email so the values are no longer hardcoded
# magic numbers — same email yields the same UUID across all seeds.
HUCE_USER_ID = seed_user_id("huce@p234.demo")
HUST_USER_ID = seed_user_id("hust@p234.demo")
CROSS_SCHOOL_USER_ID = seed_user_id("crossschool@p234.demo")

# Role IDs (USER is the merged LECTURER + LEADER + REVIEWER role).
# Legacy role UUIDs are preserved so old DB rows that still reference
# them don't break the FK; new seed only assigns USER / ADMIN.
ROLE_IDS = {
    "ADMIN": UUID("20000000-0000-0000-0000-000000000001"),
    "USER": UUID("20000000-0000-0000-0000-000000000002"),
    "LEADER": UUID("20000000-0000-0000-0000-000000000003"),
    "REVIEWER": UUID("20000000-0000-0000-0000-000000000004"),
}

# Department IDs (from existing seed_uc_demo.py)
DEPARTMENT_IDS = {
    "HUCE": UUID("050813ff-d105-4b95-aab2-fe8c7e3a33f7"),  # Existing department
    "HUST": UUID("cc8dc08f-3f47-4fd9-9cf5-8e7443b17b2c"),  # Existing department
}


USERS = [
    {
        "id": HUCE_USER_ID,
        "email": "huce@p234.demo",
        "full_name": "Nguyễn Văn A - HUCE",
        "department_id": DEPARTMENT_IDS["HUCE"],
        "department_label": "HUCE",
        "role_code": "USER",
        "role": "Người dùng",
        "description": "Người dùng thuộc Trường Đại học Kiến trúc Hà Nội",
    },
    {
        "id": HUST_USER_ID,
        "email": "hust@p234.demo",
        "full_name": "Trần Thị B - HUST",
        "department_id": DEPARTMENT_IDS["HUST"],
        "department_label": "HUST",
        "role_code": "USER",
        "role": "Người dùng",
        "description": "Người dùng thuộc Trường Đại học Bách khoa Hà Nội",
    },
    {
        "id": CROSS_SCHOOL_USER_ID,
        "email": "crossschool@p234.demo",
        "full_name": "Lê Văn C - Cross-School",
        "department_id": None,  # Will use "*" for cross-school access
        "department_label": "SUPER",
        "role_code": "ADMIN",
        "role": "Quản trị viên",
        "description": "Người dùng có quyền truy cập tất cả các trường",
    },
]


async def main() -> None:
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        echo=False,
    )

    password_hash = bcrypt.hashpw(
        b"P234@123",
        bcrypt.gensalt(),
    ).decode("utf-8")

    try:
        async with engine.begin() as connection:
            for user_data in USERS:
                # Insert user
                await connection.execute(
                    text(
                        """
                        INSERT INTO users (
                            id,
                            email,
                            password_hash,
                            full_name,
                            department_id,
                            token_version,
                            is_active
                        )
                        VALUES (
                            :id,
                            :email,
                            :password_hash,
                            :full_name,
                            :department_id,
                            0,
                            true
                        )
                        ON CONFLICT (email)
                        DO UPDATE SET
                            full_name = EXCLUDED.full_name,
                            department_id = EXCLUDED.department_id,
                            is_active = true
                        """
                    ),
                    {
                        "id": user_data["id"],
                        "email": user_data["email"],
                        "password_hash": password_hash,
                        "full_name": user_data["full_name"],
                        "department_id": user_data["department_id"],
                    },
                )

                # Assign role
                await connection.execute(
                    text(
                        """
                        INSERT INTO user_roles (
                            user_id,
                            role_id
                        )
                        SELECT
                            u.id,
                            r.id
                        FROM users u
                        CROSS JOIN roles r
                        WHERE
                            u.email = :email
                            AND r.code = :role_code
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "email": user_data["email"],
                        "role_code": user_data["role_code"],
                    },
                )

                print(f"✓ Created user: {user_data['email']}")
                print(f"  - Full name: {user_data['full_name']}")
                print(f"  - Role: {user_data['role']}")
                print(f"  - Department: {user_data['department_label']}")
                print(f"  - Description: {user_data['description']}")
                print()

        print("=" * 60)
        print("Multi-school seed completed!")
        print("=" * 60)
        print()
        print("Login credentials (all use password: P234@123):")
        print()
        print("  1. HUCE User (chỉ truy cập văn bản HUCE):")
        print("     Email: huce@p234.demo")
        print()
        print("  2. HUST User (chỉ truy cập văn bản HUST):")
        print("     Email: hust@p234.demo")
        print()
        print("  3. Cross-School User (truy cập tất cả văn bản):")
        print("     Email: crossschool@p234.demo")
        print()

    finally:
        await engine.dispose()


asyncio.run(main())
