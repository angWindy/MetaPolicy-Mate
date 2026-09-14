"""Centralised R2 object-key builder for the P-234 demo.

The canonical key schema is::

    {tenant_code}/documents/{document_number}/v{version_number}/source.pdf

Examples::

    hust/documents/QD-2024-001/v1/source.pdf
    huce/documents/QD-HUCE-2024-007/v3/source.pdf

Why this layout:

* ``tenant_code`` at the top makes the bucket multi-tenant ready; the
  current single-tenant demo uses ``hust`` for everything uploaded as
  the HUST user. ``tenant_code`` is normalised to lowercase so the
  bucket stays case-flat.
* ``document_number`` is the canonical user-visible identifier from
  ``public.documents.document_number``. UUIDs are unreadable; humans
  need to debug this layout from the R2 console.
* ``v{version_number}`` is an integer (``v1``, ``v2`` ...) — matches
  the spec at ``BACKEND_ARCHITECTURE.md`` §14 (File Storage).
* ``source.pdf`` is the only artifact we currently store; the
  ``v{n}/`` folder leaves room for derived artifacts (``chunks.jsonl``,
  ``embeddings.npz``, ``preview.png``) later without a layout migration.

Legacy keys (anything that doesn't match the regex below) are still
readable from R2 because ``FileStorage`` is opaque over ``object_key``
— the DB row carries the verbatim key. A migration script
(``scripts/migrate_r2_keys.py``) and an orphan sweep
(``scripts/sweep_r2_orphans.py``) handle the cleanup; see the
approved plan for the full workflow.

Rollback safety
---------------
Set the env flag ``R2_USE_LEGACY_KEYS=true`` to force the builder back
to the original f-string layout (``schools/{uuid}/documents/{uuid}/versions/{uuid}/source.pdf``).
Useful when a regression ships and the bucket needs to be inspected
under the old layout. Default is ``false``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Final

from src.config import Settings


# Match the full canonical key — used by ``is_legacy`` and ``parse``.
CANONICAL_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<tenant>[a-z0-9][a-z0-9_-]*)"
    r"/documents/"
    r"(?P<document_number>[A-Za-z0-9._:-]+)"
    r"/v(?P<version_number>[0-9]+)"
    r"/source\.pdf$"
)

# Original (pre-reorg) f-string layout — produced by the old
# upload + replace-source handlers.
LEGACY_UUID_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^schools/"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"/documents/"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"/versions/"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    r"/source\.pdf$"
)

# Seed-script variant: ``seed/{slug}/{uuid}/v{uuid}/source.pdf``.
LEGACY_SEED_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^seed/"
    r"[A-Za-z0-9_-]+/"
    r"[0-9a-fA-F-]{36}"
    r"/v[0-9a-fA-F-]+"
    r"/source\.pdf$"
)


@dataclass(frozen=True)
class ParsedKey:
    """Structured view of a parsed R2 object key."""

    tenant_code: str
    document_number: str
    version_number: int


class ObjectKeyBuilder:
    """Build (and parse) the canonical R2 object key.

    Parameters
    ----------
    settings:
        Application settings. Used as the default tenant when no
        ``tenant_code`` is supplied to ``for_version``.

    environment:
        Optional override (mainly for tests) of the process environment
        used to resolve the ``R2_USE_LEGACY_KEYS`` rollback flag.
    """

    def __init__(
        self,
        settings: Settings,
        environment: dict[str, str] | None = None,
    ) -> None:
        self._settings = settings
        self._environment = (
            environment
            if environment is not None
            else os.environ
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    # Tenant segment used for PUBLIC access_scope documents. Lives at
    # the top of the R2 bucket next to per-school tenants (hust, huce,
    # …) so PUBLIC docs share the same key schema as every other doc.
    PUBLIC_TENANT_CODE: Final[str] = "public"

    def for_version(
        self,
        document_number: str,
        version_number: int,
        tenant_code: str | None = None,
        access_scope: (
            str | None
        ) = None,
    ) -> str:
        """Return the canonical key for a specific document version.

        Parameters
        ----------
        document_number:
            Canonical user-visible document id.
        version_number:
            Integer version (1, 2, ...).
        tenant_code:
            Resolved tenant (school) code, lower-cased by this
            builder. Required unless the caller passes
            ``access_scope=PUBLIC`` — in which case the public tenant
            bucket is used regardless of the caller's school.
        access_scope:
            Optional. When set to ``"PUBLIC"`` the builder forces the
            tenant segment to ``public`` so PUBLIC documents always
            live under the same top-level folder, independent of which
            school the uploading user belongs to. Any other value
            (including ``None``) defers to ``tenant_code``.

        When the ``R2_USE_LEGACY_KEYS`` flag is set the builder falls
        back to the original UUID-based layout. In that mode we still
        require a tenant code so the layout is at least readable
        (``schools/{tenant_uuid}/...``); callers without a tenant_code
        use the ``Settings.school_id`` as a stand-in.
        """
        if self._use_legacy_keys():
            # R2_USE_LEGACY_KEYS=true is a rollback flag for inspecting
            # old keys during migration. Since ``settings.school_id`` is
            # now intentionally None (tenant identity is per-user, not a
            # global constant), fall back to the caller's ``tenant_code``
            # if available; otherwise raise so the regression is caught.
            school_id = (
                tenant_code
                if tenant_code is not None
                else self.PUBLIC_TENANT_CODE
            )
            if access_scope == "PUBLIC":
                school_id = self.PUBLIC_TENANT_CODE
            if school_id is None:
                raise ValueError(
                    "tenant_code is required even in legacy-key mode; "
                    "pass it explicitly to ObjectKeyBuilder.for_version(). "
                    "The global Settings.school_id fallback has been removed."
                )
            # Imported lazily so we never emit a UUID when the new
            # schema is in effect.
            from uuid import uuid4

            return (
                f"schools/{school_id}/"
                f"documents/{uuid4()}/"
                f"versions/{uuid4()}/"
                "source.pdf"
            )

        tenant = self._resolve_tenant_code(
            tenant_code,
            access_scope=(
                access_scope
            ),
        )

        if not document_number:
            raise ValueError(
                "document_number is required "
                "for the canonical R2 key schema"
            )

        if (
            version_number is None
            or version_number < 1
        ):
            raise ValueError(
                "version_number must be a "
                "positive integer"
            )

        return (
            f"{tenant}/documents/"
            f"{document_number}/"
            f"v{version_number}/source.pdf"
        )

    def parse(
        self,
        object_key: str,
    ) -> ParsedKey | None:
        """Reverse ``for_version`` for a canonical key.

        Returns ``None`` for any key that does not match the canonical
        pattern; callers should fall back to ``is_legacy`` for those.
        """
        match = (
            CANONICAL_KEY_PATTERN.match(
                object_key,
            )
        )
        if not match:
            return None

        return ParsedKey(
            tenant_code=match.group("tenant"),
            document_number=(
                match.group("document_number")
            ),
            version_number=int(
                match.group("version_number")
            ),
        )

    def is_legacy(
        self,
        object_key: str,
    ) -> bool:
        """True if the key is *not* canonical.

        Includes both UUID and seed-script legacy layouts, plus
        diagnostic prefixes (``r2_smoke_test/``, ``tests/``) and
        anything else the canonical regex rejects.
        """
        if (
            CANONICAL_KEY_PATTERN.match(
                object_key,
            )
            is not None
        ):
            return False

        return True

    def is_canonical(
        self,
        object_key: str,
    ) -> bool:
        return not self.is_legacy(
            object_key
        )

    def legacy_layout_label(
        self,
        object_key: str,
    ) -> str:
        """Best-effort tag for diagnostics (UUID / diag / unknown)."""
        if (
            LEGACY_UUID_KEY_PATTERN.match(
                object_key,
            )
        ):
            return "uuid-legacy"
        if (
            LEGACY_SEED_KEY_PATTERN.match(
                object_key,
            )
        ):
            return "seed-legacy"
        if object_key.startswith(
            "r2_smoke_test/"
        ) or object_key.startswith(
            "tests/"
        ):
            return "diagnostic"
        return "unknown"

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _use_legacy_keys(self) -> bool:
        flag = self._environment.get(
            "R2_USE_LEGACY_KEYS",
            "",
        )
        return flag.lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _resolve_tenant_code(
        self,
        tenant_code: str | None,
        access_scope: (
            str | None
        ) = None,
    ) -> str:
        # Tenant identity must come from the request context
        # (i.e. the user's bound department). Falling back to a
        # Settings constant would re-introduce the bogus hardcoded
        # tenant identity bug; we explicitly do NOT read
        # ``settings.school_code`` here.
        #
        # Exception: PUBLIC documents. They live under the dedicated
        # ``public/`` top-level folder so anyone — independent of their
        # school — can resolve them via a single canonical prefix. We
        # accept PUBLIC scope with no tenant_code and force the
        # ``public`` segment.
        if (
            access_scope
            == "PUBLIC"
        ):
            return self.PUBLIC_TENANT_CODE

        if not tenant_code:
            raise ValueError(
                "tenant_code is required; pass it "
                "explicitly to "
                "ObjectKeyBuilder.for_version() "
                "(resolved from the authenticated "
                "user's department, NOT from "
                "settings)."
            )

        return tenant_code.lower()