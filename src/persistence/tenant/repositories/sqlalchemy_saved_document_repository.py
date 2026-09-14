from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from src.domain.entities.saved_document import (
    SavedDocument,
)
from src.domain.repositories.saved_document_repository import (
    SavedDocumentRepository,
)
from src.persistence.tenant.models.saved_document import (
    SavedDocumentModel,
)


class SqlAlchemySavedDocumentRepository(
    SavedDocumentRepository
):
    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self._session = session

    async def add(
        self,
        saved: SavedDocument,
    ) -> None:
        self._session.add(
            SavedDocumentModel(
                id=saved.id,
                user_id=saved.user_id,
                document_id=saved.document_id,
                created_at=saved.created_at,
            )
        )

    async def delete(
        self,
        user_id: UUID,
        document_id: UUID,
    ) -> bool:
        result = await self._session.execute(
            select(SavedDocumentModel).where(
                SavedDocumentModel.user_id == user_id,
                SavedDocumentModel.document_id == document_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            return False
        await self._session.delete(model)
        return True

    async def check_exists(
        self,
        user_id: UUID,
        document_id: UUID,
    ) -> bool:
        result = await self._session.execute(
            select(func.count(SavedDocumentModel.id)).where(
                SavedDocumentModel.user_id == user_id,
                SavedDocumentModel.document_id == document_id,
            )
        )
        return int(result.scalar_one()) > 0

    async def list_by_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[SavedDocument], int]:
        offset = (page - 1) * page_size
        total_result = await self._session.execute(
            select(func.count(SavedDocumentModel.id)).where(
                SavedDocumentModel.user_id == user_id,
            )
        )
        total = int(total_result.scalar_one())

        result = await self._session.execute(
            select(SavedDocumentModel)
            .where(SavedDocumentModel.user_id == user_id)
            .order_by(SavedDocumentModel.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )

        items = [self._to_domain(m) for m in result.scalars().all()]
        return items, total

    @staticmethod
    def _to_domain(
        model: SavedDocumentModel,
    ) -> SavedDocument:
        return SavedDocument(
            id=model.id,
            user_id=model.user_id,
            document_id=model.document_id,
            created_at=model.created_at,
        )
