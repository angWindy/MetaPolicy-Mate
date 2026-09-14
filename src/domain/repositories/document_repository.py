from datetime import date
from typing import Protocol
from uuid import UUID

from src.domain.entities.document import (
    Document,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus,
)


class DocumentRepository(
    Protocol
):
    async def get_by_id(
        self,
        document_id: UUID,
    ) -> Document | None:
        ...

    async def get_by_ids(
        self,
        document_ids: list[UUID],
    ) -> list[Document]:
        """Batch fetch - used by ACL checks to avoid N+1.

        Returns documents that exist; missing IDs are silently
        skipped so the caller can iterate ``document_ids`` to
        detect missing entries (treated as "not accessible").
        """
        ...

    async def get_by_number(
        self,
        document_number: str,
    ) -> Document | None:
        ...

    async def exists_by_number(
        self,
        document_number: str,
        exclude_document_id: (
            UUID | None
        ) = None,
    ) -> bool:
        ...

    async def search(
        self,
        document_number: str | None,
        legal_status: (
            DocumentLegalStatus | None
        ),
        issued_from: date | None,
        issued_to: date | None,
        department_id: UUID | None,
        skip: int,
        limit: int,
        is_admin: bool = False,
    ) -> list[Document]:
        ...

    async def count(
        self,
        document_number: str | None,
        legal_status: (
            DocumentLegalStatus | None
        ),
        issued_from: date | None,
        issued_to: date | None,
        department_id: UUID | None,
        is_admin: bool = False,
    ) -> int:
        ...

    async def add(
        self,
        document: Document,
    ) -> None:
        ...

    async def update(
        self,
        document: Document,
    ) -> None:
        ...

    async def delete(
        self,
        document_id: UUID,
    ) -> None:
        ...

    async def get_documents_due_for_effectiveness(
        self,
        as_of: date,
    ) -> list[Document]:
        ...

    async def update_object_key(
        self,
        version_id: UUID,
        new_key: str,
    ) -> None:
        """Update the R2 object_key of a specific document version.

        Used by the access-scope update handler when a document moves
        between tenant segments in R2 (e.g. public/ → hust/).
        The caller is responsible for ensuring the new key is valid
        and that the R2 object has been copied to the new key before
        calling this method.
        """
        ...