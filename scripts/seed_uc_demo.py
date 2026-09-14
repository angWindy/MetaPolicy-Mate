import asyncio
import sys
from uuid import UUID

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


ADMIN_USER_ID = seed_user_id("admin@p234.demo")

ROLE_IDS = {
    "ADMIN": UUID(
        "20000000-0000-0000-0000-000000000001"
    ),
    # USER is the merged LECTURER + LEADER + REVIEWER role.
    "USER": UUID(
        "20000000-0000-0000-0000-000000000002"
    ),
    # Legacy role IDs are preserved so existing rows referencing them
    # don't break the FK. New seed does NOT create new users with
    # these roles.
    "LEADER": UUID(
        "20000000-0000-0000-0000-000000000003"
    ),
}

PERMISSION_IDS = {
    "DOCUMENT_READ": UUID(
        "30000000-0000-0000-0000-000000000001"
    ),
    "DOCUMENT_UPLOAD": UUID(
        "30000000-0000-0000-0000-000000000002"
    ),
    "DOCUMENT_UPDATE": UUID(
        "30000000-0000-0000-0000-000000000003"
    ),
    "DOCUMENT_DELETE": UUID(
        "30000000-0000-0000-0000-000000000004"
    ),
    "CHAT_USE": UUID(
        "30000000-0000-0000-0000-000000000005"
    ),
    "USER_READ": UUID(
        "30000000-0000-0000-0000-000000000006"
    ),
    "USER_MANAGE": UUID(
        "30000000-0000-0000-0000-000000000007"
    ),
    # Phase 5 RBAC expansion: these are referenced by admin/rbac
    # routers but were never seeded, so any caller hitting those
    # endpoints got a 403 even when ADMIN. Added per the approved
    # "Comprehensive E2E" plan §2.3.
    "DOCUMENT_APPROVE": UUID(
        "30000000-0000-0000-0000-000000000008"
    ),
    "DOCUMENT_PROCESS": UUID(
        "30000000-0000-0000-0000-000000000009"
    ),
    "DOCUMENT_AUDIT_READ": UUID(
        "30000000-0000-0000-0000-00000000000a"
    ),
    "ACTIVITY_LOG_READ": UUID(
        "30000000-0000-0000-0000-00000000000b"
    ),
    "RBAC_MANAGE": UUID(
        "30000000-0000-0000-0000-00000000000c"
    ),
    "ROLE_MANAGE": UUID(
        "30000000-0000-0000-0000-00000000000d"
    ),
}


ROLES = [
    {
        "id": ROLE_IDS["ADMIN"],
        "code": "ADMIN",
        "name": "Administrator",
        "description": "Tenant administrator",
        "is_system": True,
    },
    {
        "id": ROLE_IDS["USER"],
        "code": "USER",
        "name": "User",
        "description": (
            "Standard user (merged Lecturer/Leader/Reviewer "
            "on 2026-08-31)"
        ),
        "is_system": True,
    },
    {
        "id": ROLE_IDS["LEADER"],
        "code": "LEADER",
        "name": "Leader (legacy)",
        "description": (
            "Legacy role, merged into USER on 2026-08-31. "
            "Kept only for FK continuity on stale rows."
        ),
        "is_system": False,
    },
]


PERMISSIONS = [
    {
        "id": PERMISSION_IDS["DOCUMENT_READ"],
        "code": "document.read",
        "name": "Read documents",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_UPLOAD"],
        "code": "document.upload",
        "name": "Upload documents",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_UPDATE"],
        "code": "document.update",
        "name": "Update documents",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_DELETE"],
        "code": "document.delete",
        "name": "Delete documents",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["CHAT_USE"],
        "code": "chat.use",
        "name": "Use chatbot",
        "module": "chat",
    },
    {
        "id": PERMISSION_IDS["USER_READ"],
        "code": "user.read",
        "name": "Read users",
        "module": "user",
    },
    {
        "id": PERMISSION_IDS["USER_MANAGE"],
        "code": "user.manage",
        "name": "Manage users",
        "module": "user",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_APPROVE"],
        "code": "document.approve",
        "name": "Approve documents",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_PROCESS"],
        "code": "document.process",
        "name": "Process documents (digitize)",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["DOCUMENT_AUDIT_READ"],
        "code": "document.audit.read",
        "name": "Read document audit trails",
        "module": "document",
    },
    {
        "id": PERMISSION_IDS["ACTIVITY_LOG_READ"],
        "code": "activity_log.read",
        "name": "Read activity log",
        "module": "activity_log",
    },
    {
        "id": PERMISSION_IDS["RBAC_MANAGE"],
        "code": "rbac.manage",
        "name": "Manage RBAC permissions",
        "module": "rbac",
    },
    {
        "id": PERMISSION_IDS["ROLE_MANAGE"],
        "code": "role.manage",
        "name": "Manage roles",
        "module": "rbac",
    },
]


ROLE_PERMISSIONS = {
    "ADMIN": [
        "DOCUMENT_READ",
        "DOCUMENT_UPLOAD",
        "DOCUMENT_UPDATE",
        "DOCUMENT_DELETE",
        "DOCUMENT_APPROVE",
        "DOCUMENT_PROCESS",
        "DOCUMENT_AUDIT_READ",
        "ACTIVITY_LOG_READ",
        "CHAT_USE",
        "USER_READ",
        "USER_MANAGE",
        "RBAC_MANAGE",
        "ROLE_MANAGE",
    ],
    # USER = LECTURER ∪ LEADER ∪ REVIEWER (union).
    "USER": [
        "DOCUMENT_READ",
        "DOCUMENT_UPLOAD",
        "DOCUMENT_PROCESS",
        "DOCUMENT_APPROVE",
        "DOCUMENT_AUDIT_READ",
        "ACTIVITY_LOG_READ",
        "CHAT_USE",
        "USER_READ",
    ],
    # Legacy role kept for FK continuity on stale user_roles rows.
    "LEADER": [
        "DOCUMENT_READ",
        "DOCUMENT_UPLOAD",
        "DOCUMENT_APPROVE",
        "DOCUMENT_AUDIT_READ",
        "ACTIVITY_LOG_READ",
        "CHAT_USE",
        "USER_READ",
    ],
}


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

            # Roles
            for role in ROLES:
                await connection.execute(
                    text(
                        """
                        INSERT INTO roles (
                            id,
                            code,
                            name,
                            description,
                            is_system
                        )
                        VALUES (
                            :id,
                            :code,
                            :name,
                            :description,
                            :is_system
                        )
                        ON CONFLICT (code)
                        DO NOTHING
                        """
                    ),
                    role,
                )

            # Permissions
            for permission in PERMISSIONS:
                await connection.execute(
                    text(
                        """
                        INSERT INTO permissions (
                            id,
                            code,
                            name,
                            module
                        )
                        VALUES (
                            :id,
                            :code,
                            :name,
                            :module
                        )
                        ON CONFLICT (code)
                        DO NOTHING
                        """
                    ),
                    permission,
                )

            # Role permissions
            for role_code, permission_codes in (
                ROLE_PERMISSIONS.items()
            ):
                for permission_code in permission_codes:
                    await connection.execute(
                        text(
                            """
                            INSERT INTO role_permissions (
                                role_id,
                                permission_id
                            )
                            VALUES (
                                (
                                    SELECT id
                                    FROM roles
                                    WHERE code = :role_code
                                ),
                                (
                                    SELECT id
                                    FROM permissions
                                    WHERE code = :permission_code
                                )
                            )
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "role_code": role_code,
                            "permission_code":
                                PERMISSIONS_BY_KEY[
                                    permission_code
                                ],
                        },
                    )

            # Demo admin
            await connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id,
                        email,
                        password_hash,
                        full_name,
                        department,
                        token_version,
                        is_active,
                        is_admin
                    )
                    VALUES (
                        :id,
                        :email,
                        :password_hash,
                        :full_name,
                        :department,
                        0,
                        true,
                        true
                    )
                    ON CONFLICT (email)
                    DO NOTHING
                    """
                ),
                {
                    "id": ADMIN_USER_ID,
                    "email": "admin@p234.demo",
                    "password_hash": password_hash,
                    "full_name": "P234 Demo Admin",
                    "department": "Administration",
                },
            )

            # Admin role
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
                        AND r.code = 'ADMIN'
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "email": "admin@p234.demo",
                },
            )

        print("Seed completed.")

    finally:
        await engine.dispose()


PERMISSIONS_BY_KEY = {
    key: value["code"]
    for key, value in zip(
        PERMISSION_IDS.keys(),
        PERMISSIONS,
    )
}


asyncio.run(main())