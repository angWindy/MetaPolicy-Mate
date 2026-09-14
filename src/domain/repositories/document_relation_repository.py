from typing import Protocol
from uuid import UUID

from src.domain.entities.document_relation import (
    DocumentRelation,
)


class DocumentRelationRepository(
    Protocol
):
    async def get_by_id(
        self,
        relation_id: UUID,
    ) -> DocumentRelation | None:
        ...

    async def get_by_document_id(
        self,
        document_id: UUID,
    ) -> list[DocumentRelation]:
        ...

    async def get_effective_superseding_relation(
        self,
        target_document_id: UUID,
    ) -> DocumentRelation | None:
        ...

    async def add(
        self,
        relation: DocumentRelation,
    ) -> None:
        ...

    async def delete(
        self,
        relation: DocumentRelation,
    ) -> None:
        ...