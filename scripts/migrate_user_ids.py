"""Remap demo user IDs from the old hardcoded ``11111111-…`` set to the
new UUIDv5-based values produced by ``scripts._seed_ids.seed_user_id``.

Why this exists
---------------
Seed scripts historically hardcoded magic-number UUIDs (e.g.
``11111111-1111-1111-1111-111111111111`` for the demo admin). Starting
2026-09-05 those values are derived from a stable project namespace via
UUIDv5 so the same email always maps to the same ID — see
``scripts/_seed_ids.py``. To bring the live database in sync we rewrite
the existing rows in a single transaction.

Why we cannot rely on FK CASCADE / ``SET session_replication_role``
-------------------------------------------------------------------
PostgreSQL's FK constraints default to ``ON UPDATE NO ACTION`` so a PK
change blocks until every referencing row is updated first. Neon grants
the application role ``neondb_owner`` only DML privileges
(``SELECT/INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER/REFERENCES``) and not
``ALTER`` or ``SET session_replication_role``, so we cannot drop the
constraints or downgrade the trigger system for the migration.

Workaround
----------
For each (old_id, new_id) we run an INSERT-then-redirect-then-DELETE
cycle inside one transaction:

1.  Rename the old user's email to a sentinel ``migrating_<uuid>@local``
    so the unique-email constraint does not block the new row.
2.  ``INSERT INTO users(id, email, ...) SELECT new_id, original_email,
    ...`` — copies every column from the old row into a brand-new row.
3.  Update every FK column (8 tables + audit_logs.actor_id) and the
    audit_outbox.payload text to point at the new UUID.
4.  ``DELETE FROM users WHERE id = old_id``.

The whole sequence is wrapped in a single ``engine.begin()`` transaction
so any failure rolls everything back. The migration is also idempotent:
re-running after a successful apply is a no-op (the new IDs are already
in place).

Side effects
------------
After the rewrite the in-flight JWTs in browsers still carry the old
``sub`` UUID. We bump ``users.token_version`` so the existing tokens
fail validation on their next request and the browser is forced to
re-login. ``refresh_tokens`` are deleted for the same reason — they hold
a reference to the old user id and would survive the bump otherwise.

Usage
-----
    # Read-only preview:
    python scripts/migrate_user_ids.py --dry-run

    # Apply:
    python scripts/migrate_user_ids.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text

# Resolve DATABASE_URL from the same .env files the rest of the project
# uses so the script can be run from any cwd.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import dotenv_values  # type: ignore
except ImportError:
    dotenv_values = None  # type: ignore

from scripts._seed_ids import DEMO_USER_IDS, seed_user_id  # noqa: E402


# All columns that hold a user UUID (FK or otherwise) and must be
# rewritten when a user's PK changes. Keep this list in sync with
# ``database/schema.sql`` and any new column that references users.id.
USER_FK_COLUMNS: list[tuple[str, str]] = [
    ("public", "user_roles", "user_id"),
    ("public", "answer_feedbacks", "reported_by_user_id"),
    ("public", "answer_feedbacks", "reviewed_by_user_id"),
    ("public", "chat_sessions", "user_id"),
    ("public", "document_section_metadata_drafts", "reviewed_by"),
    ("public", "refresh_tokens", "user_id"),
    ("public", "saved_documents", "user_id"),
    ("public", "notifications", "user_id"),
    ("public", "user_activity_logs", "user_id"),
]

# Non-FK user reference: audit_logs.actor_id is uuid without FK
# constraint. It can refer to users, systems, etc., so we filter on
# actor_type = 'user' inside the migration.
AUDIT_LOG_ACTOR = ("public", "audit_logs", "actor_id", "actor_type", "user")

# Text columns that may embed user UUIDs as substrings (JSON payloads
# serialised to text, etc.). Plain ``REPLACE()`` is enough because UUIDs
# are fixed-width strings.
USER_TEXT_COLUMNS: list[tuple[str, str, str]] = [
    ("public", "audit_outbox", "payload"),
    ("public", "audit_outbox", "error"),
]


def _resolve_database_url() -> str:
    if url := os.environ.get("DATABASE_URL"):
        return url

    if dotenv_values is None:
        raise RuntimeError(
            "DATABASE_URL is not set and python-dotenv is not installed; "
            "either export DATABASE_URL or install python-dotenv."
        )

    for candidate in (".env", ".env.rag"):
        env_path = PROJECT_ROOT / candidate
        if env_path.exists():
            values = dotenv_values(env_path)
            if url := values.get("DATABASE_URL"):
                return url

    raise RuntimeError(
        "DATABASE_URL not found in environment or in .env / .env.rag"
    )


def _current_user_rows(conn) -> list[tuple[str, UUID, str]]:
    """Return (email, current_id, full_name) for every demo user."""
    rows = conn.execute(
        text(
            """
            SELECT email, id, full_name
            FROM public.users
            ORDER BY email
            """
        )
    ).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _print_plan(email_to_current: dict[str, UUID]) -> int:
    print("=" * 72)
    print("Migration plan — remap demo users to UUIDv5-derived IDs")
    print("=" * 72)
    print(
        f"{'email':32s}  {'current id':36s}  new id"
    )
    print("-" * 110)
    changes = 0
    for email in sorted(set(DEMO_USER_IDS) | set(email_to_current)):
        current = email_to_current.get(email)
        new = DEMO_USER_IDS.get(email) or seed_user_id(email)
        marker = ""
        if current is None:
            marker = "(not in DB — will be seeded by other scripts)"
        elif current == new:
            marker = "(already up to date — skip)"
        else:
            changes += 1
        print(
            f"{email:32s}  {str(current or '-'):36s}  {new}  {marker}"
        )
    print("-" * 110)
    print(f"Rows that need PK rewrite: {changes}")
    print()
    print(f"FK columns that will be rewritten in the same transaction:")
    for schema, table, column in USER_FK_COLUMNS:
        print(f"  - {schema}.{table}.{column}")
    print(
        f"  - {AUDIT_LOG_ACTOR[0]}.{AUDIT_LOG_ACTOR[1]}.{AUDIT_LOG_ACTOR[2]} "
        f"(filtered on {AUDIT_LOG_ACTOR[3]} = '{AUDIT_LOG_ACTOR[4]}')"
    )
    print(f"Text columns that get a UUID string REPLACE():")
    for schema, table, column in USER_TEXT_COLUMNS:
        print(f"  - {schema}.{table}.{column}")
    print()
    print("Side effects:")
    print("  - users.token_version bumped (forces re-login)")
    print("  - refresh_tokens rows deleted (old token refs are stale)")
    return changes


def _fk_rewrite_counts(
    conn, old_to_new: dict[UUID, UUID]
) -> dict[tuple[str, str], int]:
    """Count how many rows in each FK table refer to an old UUID."""
    counts: dict[tuple[str, str], int] = {}
    placeholders = ", ".join(f":old_{i}" for i in range(len(old_to_new)))
    params = {f"old_{i}": v for i, v in enumerate(old_to_new.keys())}

    for schema, table, column in USER_FK_COLUMNS:
        row = conn.execute(
            text(
                f"""
                SELECT COUNT(*) FROM {schema}.{table}
                WHERE {column} IN ({placeholders})
                """
            ),
            params,
        ).scalar_one()
        counts[(table, column)] = int(row)

    row = conn.execute(
        text(
            f"""
            SELECT COUNT(*) FROM {AUDIT_LOG_ACTOR[0]}.{AUDIT_LOG_ACTOR[1]}
            WHERE {AUDIT_LOG_ACTOR[2]} IN ({placeholders})
              AND {AUDIT_LOG_ACTOR[3]} = :actor_type
            """
        ),
        {**params, "actor_type": AUDIT_LOG_ACTOR[4]},
    ).scalar_one()
    counts[(AUDIT_LOG_ACTOR[1], AUDIT_LOG_ACTOR[2])] = int(row)

    return counts


def _apply_migration(engine) -> None:
    """Run the migration inside a single transaction.

    For each (old_id, new_id) the cycle is:

      1. Rename old user's email to ``migrating_<old_id>@local`` to
         free the unique-email slot.
      2. INSERT new user row with the same data as the old one.
      3. UPDATE every FK column / audit_outbox payload to the new id.
      4. DELETE the old user row.

    Order matters: step 3 is safe because the new row from step 2
    already satisfies every FK constraint that was previously pointing
    at the old row.
    """
    with engine.begin() as conn:
        current_rows = _current_user_rows(conn)
        email_to_current = {email: current for email, current, _ in current_rows}

        old_to_new: dict[UUID, UUID] = {}
        for email, current_id, _ in current_rows:
            target = DEMO_USER_IDS.get(email) or seed_user_id(email)
            if current_id != target:
                old_to_new[current_id] = target

        if not old_to_new:
            print("No users need remapping — database already matches the new IDs.")
            return

        fk_counts = _fk_rewrite_counts(conn, old_to_new)
        print("FK rewrite counts (will execute in same transaction):")
        for (table, column), count in fk_counts.items():
            print(f"  {table}.{column}: {count} row(s)")
        print()

        for old_id, new_id in old_to_new.items():
            # The old row's email is captured by mapping the old_id back
            # to the original email through the current_rows snapshot.
            original_email = next(
                email for email, current_id, _ in current_rows
                if current_id == old_id
            )
            sentinel_email = f"migrating_{old_id}@p234.local"

            # 1) Move the old user's email out of the way so the new
            #    row can reuse it without violating the UNIQUE
            #    constraint on users.email.
            conn.execute(
                text(
                    "UPDATE public.users SET email = :sentinel WHERE id = :old"
                ),
                {"sentinel": sentinel_email, "old": old_id},
            )

            # 2) Insert the new user row, copying every column from the
            #    old row. Done in two statements so the email we just
            #    renamed is not pulled back into the new row.
            conn.execute(
                text(
                    """
                    INSERT INTO public.users (
                        id, email, password_hash, full_name, department_id,
                        token_version, is_active, is_admin, created_at, updated_at
                    )
                    SELECT
                        :new_id, :original_email, password_hash, full_name,
                        department_id, token_version, is_active, is_admin,
                        created_at, updated_at
                    FROM public.users
                    WHERE id = :old_id
                    """
                ),
                {
                    "new_id": new_id,
                    "original_email": original_email,
                    "old_id": old_id,
                },
            )

            # 3) Rewrite FK columns now that the new row exists.
            for schema, table, column in USER_FK_COLUMNS:
                conn.execute(
                    text(
                        f"UPDATE {schema}.{table} SET {column} = :new "
                        f"WHERE {column} = :old"
                    ),
                    {"old": old_id, "new": new_id},
                )

            # audit_logs.actor_id, restricted to user-typed actors.
            conn.execute(
                text(
                    f"""
                    UPDATE {AUDIT_LOG_ACTOR[0]}.{AUDIT_LOG_ACTOR[1]}
                    SET {AUDIT_LOG_ACTOR[2]} = :new
                    WHERE {AUDIT_LOG_ACTOR[2]} = :old
                      AND {AUDIT_LOG_ACTOR[3]} = :actor_type
                    """
                ),
                {
                    "old": old_id,
                    "new": new_id,
                    "actor_type": AUDIT_LOG_ACTOR[4],
                },
            )

            # Text columns where the UUID may appear as a substring
            # (JSON payloads etc.). REPLACE() handles it as a plain
            # string swap because UUIDs are fixed-width.
            for schema, table, column in USER_TEXT_COLUMNS:
                conn.execute(
                    text(
                        f"UPDATE {schema}.{table} "
                        f"SET {column} = REPLACE({column}, :old, :new) "
                        f"WHERE {column} LIKE :pattern"
                    ),
                    {
                        "old": str(old_id),
                        "new": str(new_id),
                        "pattern": f"%{old_id}%",
                    },
                )

            # 4) Drop the old user row now that nothing references it.
            conn.execute(
                text("DELETE FROM public.users WHERE id = :old"),
                {"old": old_id},
            )

        # 5) Invalidate auth state for every user that was remapped.
        new_ids = [str(v) for v in old_to_new.values()]
        conn.execute(
            text(
                """
                UPDATE public.users
                SET token_version = token_version + 1
                WHERE id = ANY(CAST(:new_ids AS uuid[]))
                """
            ),
            {"new_ids": new_ids},
        )
        conn.execute(
            text(
                """
                DELETE FROM public.refresh_tokens
                WHERE user_id = ANY(CAST(:new_ids AS uuid[]))
                """
            ),
            {"new_ids": new_ids},
        )

    print(
        f"Applied {len(old_to_new)} user PK remap(s) + FK rewrite(s); "
        f"token_version bumped and refresh tokens deleted."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the migration plan without modifying anything.",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Apply the migration in a single transaction.",
    )
    args = parser.parse_args()

    db_url = _resolve_database_url()
    print(f"Connecting to: {db_url.split('@')[-1]}")  # don't echo password
    engine = create_engine(db_url)

    with engine.connect() as conn:
        current_rows = _current_user_rows(conn)
        email_to_current = {email: current for email, current, _ in current_rows}

    changes = _print_plan(email_to_current)
    if changes == 0:
        return 0

    if args.dry_run:
        print("DRY RUN — no changes applied.")
        return 0

    # Final confirmation prompt for --apply.
    if sys.stdin.isatty():
        answer = input("Type 'yes' to apply: ").strip().lower()
        if answer != "yes":
            print("Aborted by user.")
            return 1

    _apply_migration(engine)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
