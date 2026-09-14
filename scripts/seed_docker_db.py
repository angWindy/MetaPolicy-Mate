"""
Standalone seed script to initialize docker postgres with all necessary tables
and demo users for multi-school access testing.
"""

import asyncio
import sys
from uuid import UUID, uuid4

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Demo user UUIDs are derived from a stable namespace via UUIDv5 so the
# same email always resolves to the same ID across runs. See
# ``scripts/_seed_ids.py`` for the stability contract and the rationale
# for moving away from the old ``11111111-…`` magic numbers.
from scripts._seed_ids import DEMO_USER_IDS, seed_user_id

# Database URL for docker postgres
DOCKER_DB_URL = "postgresql+psycopg://p234:p234@localhost:5432/p234"

# Role IDs (USER is the merged LECTURER + LEADER + REVIEWER role).
ROLE_IDS = {
    "ADMIN": UUID("20000000-0000-0000-0000-000000000001"),
    "USER": UUID("20000000-0000-0000-0000-000000000002"),
    # Kept as legacy IDs so old DB rows that still reference
    # LECTURER/LEADER/REVIEWER don't break the FK; new seed does
    # NOT create users on these.
    "LEADER": UUID("20000000-0000-0000-0000-000000000003"),
    "REVIEWER": UUID("20000000-0000-0000-0000-000000000004"),
}

# Permission IDs
PERMISSION_IDS = {
    "DOCUMENT_READ": UUID("30000000-0000-0000-0000-000000000001"),
    "DOCUMENT_UPLOAD": UUID("30000000-0000-0000-0000-000000000002"),
    "DOCUMENT_UPDATE": UUID("30000000-0000-0000-0000-000000000003"),
    "DOCUMENT_DELETE": UUID("30000000-0000-0000-0000-000000000004"),
    "CHAT_USE": UUID("30000000-0000-0000-0000-000000000005"),
    "USER_READ": UUID("30000000-0000-0000-0000-000000000006"),
    "USER_MANAGE": UUID("30000000-0000-0000-0000-000000000007"),
    "DOCUMENT_APPROVE": UUID("30000000-0000-0000-0000-000000000008"),
    "DOCUMENT_PROCESS": UUID("30000000-0000-0000-0000-000000000009"),
    "DOCUMENT_AUDIT_READ": UUID("30000000-0000-0000-0000-00000000000a"),
    "ACTIVITY_LOG_READ": UUID("30000000-0000-0000-0000-00000000000b"),
    "RBAC_MANAGE": UUID("30000000-0000-0000-0000-00000000000c"),
    "ROLE_MANAGE": UUID("30000000-0000-0000-0000-00000000000d"),
}

# Department IDs
DEPARTMENT_IDS = {
    "HUCE": UUID("050813ff-d105-4b95-aab2-fe8c7e3a33f7"),
    "HUST": UUID("cc8dc08f-3f47-4fd9-9cf5-8e7443b17b2c"),
}

# Demo user IDs are derived from the user's email via UUIDv5 so the
# values are no longer hardcoded magic numbers. See scripts/_seed_ids.py.
ADMIN_USER_ID = seed_user_id("admin@p234.demo")
REVIEWER_USER_ID = seed_user_id("reviewer@p234.demo")
LECTURER_USER_ID = seed_user_id("user@p234.demo")

HUCE_USER_ID = seed_user_id("huce@p234.demo")
HUST_USER_ID = seed_user_id("hust@p234.demo")
CROSS_SCHOOL_USER_ID = seed_user_id("crossschool@p234.demo")

PASSWORD_HASH = bcrypt.hashpw(b"P234@123", bcrypt.gensalt()).decode("utf-8")


async def create_schema(connection):
    """Create all necessary tables for the demo."""
    
    # Users table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(500) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            department_id UUID,
            token_version INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            is_admin BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """))
    
    # Roles table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS roles (
            id UUID PRIMARY KEY,
            code VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            is_system BOOLEAN DEFAULT false
        )
    """))
    
    # Permissions table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS permissions (
            id UUID PRIMARY KEY,
            code VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            module VARCHAR(100)
        )
    """))
    
    # User roles table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id UUID NOT NULL,
            role_id UUID NOT NULL,
            PRIMARY KEY (user_id, role_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
        )
    """))
    
    # Role permissions table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id UUID NOT NULL,
            permission_id UUID NOT NULL,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
        )
    """))
    
    # Departments table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS departments (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(50) NOT NULL UNIQUE,
            school_id UUID
        )
    """))
    
    # Documents table (simplified for demo)
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY,
            document_number VARCHAR(200) NOT NULL UNIQUE,
            title VARCHAR(500) NOT NULL,
            issued_by VARCHAR(500),
            owner_department VARCHAR(200),
            access_level VARCHAR(30) DEFAULT 'internal',
            allowed_departments JSONB DEFAULT '[]',
            school_id UUID,
            legal_status VARCHAR(30) DEFAULT 'DANG_HIEU_LUC',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """))
    
    # Document versions table
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS document_versions (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            issued_date DATE,
            effective_from DATE,
            effective_to DATE,
            legal_status VARCHAR(30) DEFAULT 'DANG_HIEU_LUC',
            processing_status VARCHAR(30) DEFAULT 'published',
            checksum VARCHAR(64),
            source_filename VARCHAR(500),
            source_path VARCHAR(2000),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, version_number)
        )
    """))
    
    print("✓ Schema created successfully")


async def seed_roles(connection):
    """Seed roles and permissions."""
    
    roles = [
        {"id": ROLE_IDS["ADMIN"], "code": "ADMIN", "name": "Administrator", "description": "Tenant administrator"},
        {"id": ROLE_IDS["USER"], "code": "USER", "name": "User", "description": "Standard user (merged Lecturer/Leader/Reviewer)"},
        # Legacy roles preserved so existing user_roles FKs keep
        # pointing at a real row. Marked not is_system so admins can
        # prune them once the migration is complete.
        {"id": ROLE_IDS["LEADER"], "code": "LEADER", "name": "Leader (legacy)", "description": "Merged into USER on 2026-08-31", "is_system": False},
        {"id": ROLE_IDS["REVIEWER"], "code": "REVIEWER", "name": "Reviewer (legacy)", "description": "Merged into USER on 2026-08-31", "is_system": False},
    ]
    
    permissions = [
        {"id": PERMISSION_IDS["DOCUMENT_READ"], "code": "document.read", "name": "Read documents", "module": "document"},
        {"id": PERMISSION_IDS["DOCUMENT_UPLOAD"], "code": "document.upload", "name": "Upload documents", "module": "document"},
        {"id": PERMISSION_IDS["DOCUMENT_UPDATE"], "code": "document.update", "name": "Update documents", "module": "document"},
        {"id": PERMISSION_IDS["DOCUMENT_DELETE"], "code": "document.delete", "name": "Delete documents", "module": "document"},
        {"id": PERMISSION_IDS["CHAT_USE"], "code": "chat.use", "name": "Use chatbot", "module": "chat"},
        {"id": PERMISSION_IDS["USER_READ"], "code": "user.read", "name": "Read users", "module": "user"},
        {"id": PERMISSION_IDS["USER_MANAGE"], "code": "user.manage", "name": "Manage users", "module": "user"},
        {"id": PERMISSION_IDS["DOCUMENT_APPROVE"], "code": "document.approve", "name": "Approve documents", "module": "document"},
        {"id": PERMISSION_IDS["DOCUMENT_PROCESS"], "code": "document.process", "name": "Process documents (digitize)", "module": "document"},
        {"id": PERMISSION_IDS["DOCUMENT_AUDIT_READ"], "code": "document.audit.read", "name": "Read document audit trails", "module": "document"},
        {"id": PERMISSION_IDS["ACTIVITY_LOG_READ"], "code": "activity_log.read", "name": "Read activity log", "module": "activity_log"},
        {"id": PERMISSION_IDS["RBAC_MANAGE"], "code": "rbac.manage", "name": "Manage RBAC permissions", "module": "rbac"},
        {"id": PERMISSION_IDS["ROLE_MANAGE"], "code": "role.manage", "name": "Manage roles", "module": "rbac"},
    ]
    
    role_permissions = {
        "ADMIN": [
            "document.read", "document.upload", "document.update",
            "document.delete", "document.approve", "document.process",
            "document.audit.read", "activity_log.read", "chat.use",
            "user.read", "user.manage",
            "rbac.manage", "role.manage",
        ],
        # USER is the merged role (LECTURER + LEADER + REVIEWER). It
        # gets the union of all three permission sets so existing
        # functionality is preserved.
        "USER": [
            "document.read", "document.upload", "document.process",
            "document.approve", "document.audit.read",
            "activity_log.read", "chat.use", "user.read",
        ],
        # Legacy roles: keep them readable + chat-only so any stale
        # rows still produce a meaningful (but read-only) token.
        "LEADER": [
            "document.read", "document.upload",
            "document.approve", "document.audit.read",
            "activity_log.read", "chat.use", "user.read",
        ],
        "REVIEWER": [
            "document.read", "document.upload",
            "document.process", "chat.use",
        ],
    }
    
    # Insert roles
    for role in roles:
        await connection.execute(
            text("""
                INSERT INTO roles (id, code, name, description, is_system)
                VALUES (:id, :code, :name, :description, true)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
            """),
            role
        )
    
    # Insert permissions
    for perm in permissions:
        await connection.execute(
            text("""
                INSERT INTO permissions (id, code, name, module)
                VALUES (:id, :code, :name, :module)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name
            """),
            perm
        )
    
    # Insert role permissions
    for role_code, perm_codes in role_permissions.items():
        for perm_code in perm_codes:
            await connection.execute(
                text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id FROM roles r, permissions p
                    WHERE r.code = :role_code AND p.code = :perm_code
                    ON CONFLICT DO NOTHING
                """),
                {"role_code": role_code, "perm_code": f"{perm_codes[perm_codes.index(perm_code)].lower() if perm_code == 'DOCUMENT_READ' else 'document.read'}"}
            )
    
    print("✓ Roles and permissions seeded")


async def seed_departments(connection):
    """Seed departments."""
    
    departments = [
        {"id": DEPARTMENT_IDS["HUCE"], "name": "Trường Đại học Kiến trúc Hà Nội", "code": "HUCE"},
        {"id": DEPARTMENT_IDS["HUST"], "name": "Trường Đại học Bách khoa Hà Nội", "code": "HUST"},
    ]
    
    for dept in departments:
        await connection.execute(
            text("""
                INSERT INTO departments (id, name, code)
                VALUES (:id, :name, :code)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name
            """),
            dept
        )
    
    print("✓ Departments seeded")


async def seed_users(connection):
    """Seed demo users."""
    
    users = [
        # Original demo users
        {
            "id": ADMIN_USER_ID,
            "email": "admin@p234.demo",
            "full_name": "P234 Demo Admin",
            "department_id": DEPARTMENT_IDS["HUCE"],
            "role_code": "ADMIN",
        },
        # Legacy reviewer user — keep role on the legacy REVIEWER id
        # so any existing rows referencing REVIEWER still resolve.
        {
            "id": REVIEWER_USER_ID,
            "email": "reviewer@p234.demo",
            "full_name": "P234 Demo Reviewer (legacy)",
            "department_id": DEPARTMENT_IDS["HUCE"],
            "role_code": "REVIEWER",
        },
        {
            "id": LECTURER_USER_ID,
            "email": "user@p234.demo",
            "full_name": "P234 Demo User",
            "department_id": DEPARTMENT_IDS["HUST"],
            "role_code": "USER",
        },
        # New multi-school users
        {
            "id": HUCE_USER_ID,
            "email": "huce@p234.demo",
            "full_name": "Nguyễn Văn A - HUCE",
            "department_id": DEPARTMENT_IDS["HUCE"],
            "role_code": "USER",
        },
        {
            "id": HUST_USER_ID,
            "email": "hust@p234.demo",
            "full_name": "Trần Thị B - HUST",
            "department_id": DEPARTMENT_IDS["HUST"],
            "role_code": "USER",
        },
        {
            "id": CROSS_SCHOOL_USER_ID,
            "email": "crossschool@p234.demo",
            "full_name": "Lê Văn C - Cross-School Admin",
            "department_id": None,
            "role_code": "ADMIN",
        },
    ]
    
    for user in users:
        # Insert user. ``is_admin`` is True for users with ADMIN role
        # (admin@p234.demo and crossschool@p234.demo) so the document
        # access policy can bypass the per-school department filter.
        is_admin_flag = (
            user.get("role_code") == "ADMIN"
        )
        await connection.execute(
            text("""
                INSERT INTO users (id, email, password_hash, full_name, department_id, token_version, is_active, is_admin)
                VALUES (:id, :email, :password_hash, :full_name, :department_id, 0, true, :is_admin)
                ON CONFLICT (email) DO UPDATE SET
                    full_name = EXCLUDED.full_name,
                    department_id = EXCLUDED.department_id,
                    is_active = true,
                    is_admin = EXCLUDED.is_admin
            """),
            {
                **user,
                "password_hash": PASSWORD_HASH,
                "is_admin": is_admin_flag,
            }
        )
        
        # Assign role
        await connection.execute(
            text("""
                INSERT INTO user_roles (user_id, role_id)
                SELECT u.id, r.id FROM users u, roles r
                WHERE u.email = :email AND r.code = :role_code
                ON CONFLICT DO NOTHING
            """),
            user
        )
    
    print("✓ Users seeded")


async def main() -> None:
    engine = create_async_engine(DOCKER_DB_URL, echo=False)
    
    try:
        async with engine.begin() as connection:
            # Create schema
            await create_schema(connection)
            
            # Seed data
            await seed_roles(connection)
            await seed_departments(connection)
            await seed_users(connection)
            
            # Fix role permissions properly
            await connection.execute(
                text("DELETE FROM role_permissions")
            )

            role_perm_map = {
                "ADMIN": [
                    "document.read", "document.upload", "document.update",
                    "document.delete", "document.approve", "document.process",
                    "document.audit.read", "activity_log.read",
                    "chat.use", "user.read", "user.manage",
                    "rbac.manage", "role.manage",
                ],
                # USER = LECTURER + LEADER + REVIEWER merged (union).
                "USER": [
                    "document.read", "document.upload",
                    "document.process", "document.approve",
                    "document.audit.read", "activity_log.read",
                    "chat.use", "user.read",
                ],
                # Legacy roles kept for FK continuity.
                "LEADER": [
                    "document.read", "document.upload",
                    "document.approve", "document.audit.read",
                    "activity_log.read", "chat.use", "user.read",
                ],
                "REVIEWER": [
                    "document.read", "document.upload",
                    "document.process", "chat.use",
                ],
            }
            
            for role_code, perm_codes in role_perm_map.items():
                for perm_code in perm_codes:
                    await connection.execute(
                        text("""
                            INSERT INTO role_permissions (role_id, permission_id)
                            SELECT r.id, p.id FROM roles r, permissions p
                            WHERE r.code = :role_code AND p.code = :perm_code
                            ON CONFLICT DO NOTHING
                        """),
                        {"role_code": role_code, "perm_code": perm_code}
                    )
            
            await connection.commit()
            
        print()
        print("=" * 60)
        print("Docker database seed completed!")
        print("=" * 60)
        print()
        print("Login credentials (password: P234@123):")
        print()
        print("  1. admin@p234.demo - ADMIN (cross-school)")
        print("  2. reviewer@p234.demo - REVIEWER (legacy role, kept for FK)")
        print("  3. user@p234.demo - USER (merged Lecturer/Leader/Reviewer)")
        print()
        print("  4. huce@p234.demo - HUCE User (only HUCE documents)")
        print("  5. hust@p234.demo - HUST User (only HUST documents)")
        print("  6. crossschool@p234.demo - Cross-School Admin (all documents)")
        print()
        
    finally:
        await engine.dispose()


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

asyncio.run(main())
