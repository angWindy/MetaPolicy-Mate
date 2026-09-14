"""Deterministic IDs for demo/seed users and roles.

Replaces the previous hardcoded ``11111111-1111-1111-1111-111111111111``
style UUIDs with UUIDv5 derived from a fixed project namespace plus the
user's identifier (email or role code).

Why UUIDv5
----------
The deterministic property is important: tests, JWT fixtures, and
downstream demo data need to reference the same user across runs. UUIDv5
is a one-way SHA-1 hash, so re-running it on the same input gives the
same output. The result still looks like a normal random UUID — no
obvious magic numbers — but any reader of the code can re-derive the
same value by calling ``seed_user_id(email)``.

Stability contract
------------------
The namespace UUID below MUST NEVER change. It is the project-wide
constant that gives every P-234 demo UUID its root identity.
Regenerating the namespace would silently re-map every user and break
every FK in the database. The namespace itself was computed once via
``uuid.uuid5(NAMESPACE_DNS, "p234-policymeta:demo-user-namespace:v1")``
and pinned at ``f2ae5c3b-1595-57f0-a692-1c74a92d9c1c``.

If you need a new demo user that is not on this list, call
``seed_user_id("new@example.com")`` from your script — do NOT add
another hardcoded UUID literal anywhere.
"""

from __future__ import annotations

from uuid import UUID, uuid5


# Pinned namespace UUIDv5 — see module docstring for stability contract.
P234_DEMO_USER_NAMESPACE: UUID = UUID("f2ae5c3b-1595-57f0-a692-1c74a92d9c1c")


def seed_user_id(email: str) -> UUID:
    """Return a deterministic UUID for a demo user identified by email.

    >>> seed_user_id("admin@p234.demo")  # doctest: +SKIP
    UUID('934f0e49-4e71-531f-857c-071b474c36f8')

    The result is stable across Python processes, machines, and time.
    """
    if not email or not email.strip():
        raise ValueError("seed_user_id requires a non-empty email")
    return uuid5(P234_DEMO_USER_NAMESPACE, f"user:{email.strip().lower()}")


# Canonical demo emails and their pre-computed IDs. These are exposed
# so test fixtures can ``from scripts._seed_ids import DEMO_USER_IDS``
# instead of hardcoding literals. The values below are produced by
# ``seed_user_id(<email>)`` — keep them in sync by re-running the
# ``scripts/_seed_ids.py`` doctest whenever the namespace moves.
DEMO_USER_IDS: dict[str, UUID] = {
    "admin@p234.demo": UUID("934f0e49-4e71-531f-857c-071b474c36f8"),
    "reviewer@p234.demo": UUID("94024739-710f-525e-8f0e-e26a438ed9e6"),
    "user@p234.demo": UUID("95105bbf-dce0-5e7e-9442-a3fda3eefb87"),
    "huce@p234.demo": UUID("1caf1882-efae-5e2e-bfa4-78cc3c3bf22f"),
    "hust@p234.demo": UUID("b26cf6da-f522-51ed-bf9c-c10aa670b686"),
    "crossschool@p234.demo": UUID("620956c1-529e-5678-be48-9a45b4410357"),
}


def assert_in_sync() -> None:
    """Sanity check that DEMO_USER_IDS matches a fresh derivation.

    Useful from migration scripts to fail fast if someone hand-edited a
    UUID literal in this file.
    """
    for email, expected in DEMO_USER_IDS.items():
        actual = seed_user_id(email)
        if actual != expected:
            raise RuntimeError(
                f"DEMO_USER_IDS out of sync: {email} expected={expected} "
                f"got={actual}. Did the namespace change?"
            )


if __name__ == "__main__":
    assert_in_sync()
    print("scripts/_seed_ids.py: namespace + DEMO_USER_IDS in sync")
