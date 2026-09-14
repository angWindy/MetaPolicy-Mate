"""Access scope enum for document-level ACL.

.. deprecated::
   This module is kept for backward compatibility with existing imports.
   All new code should import ``AccessScope`` from ``src.domain.schemas``,
   which is the canonical source of truth per AGENTS.md.

   Migration (one-time): replace::

       from src.domain.enums.document_access_scope import DocumentAccessScope

   with::

       from src.domain.schemas import AccessScope as DocumentAccessScope

   Both enums carry identical UPPERCASE values (``PUBLIC`` / ``DEPARTMENT``),
   so no call-site changes are required beyond the import line.
"""

from src.domain.schemas import AccessScope as DocumentAccessScope

__all__ = ["DocumentAccessScope"]
